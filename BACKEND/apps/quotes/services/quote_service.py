"""Business logic for travel assistance quotes."""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.constants import QUOTE_CREATED, QUOTE_PASSENGERS_SAVED, QUOTE_REQUOTED, QUOTE_PRODUCT_SELECTED
from apps.audit.services.audit_log import log_audit_event
from apps.catalogs.services import resolve_destination
from apps.integrations.clients import LeadCotizadorClient
from apps.integrations.exceptions import IntegrationError, SiebelBusinessError, SiebelSoapError
from apps.quotes.models import QuotePassenger, QuoteProduct, QuoteProductAttribute, TravelQuote
from apps.quotes.services.commercial_assignment import assign_commercial_for_quote

logger = logging.getLogger(__name__)


class QuoteServiceError(Exception):
    """Raised when quote operations fail validation or integration."""


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_siebel_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime('%m/%d/%Y')
    if isinstance(value, str):
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
            try:
                return datetime.strptime(value, fmt).strftime('%m/%d/%Y')
            except ValueError:
                continue
    raise QuoteServiceError(f'Fecha inválida: {value}')


def _ensure_ua_configured() -> None:
    missing = [
        name for name, value in {
            'UA_SIEBEL_USERNAME': settings.UA_SIEBEL_USERNAME,
            'UA_SIEBEL_PASSWORD': settings.UA_SIEBEL_PASSWORD,
            'UA_ORGANIZATION_ID': settings.UA_ORGANIZATION_ID,
        }.items()
        if not value
    ]
    if missing:
        raise QuoteServiceError(
            'Integración UA no configurada. Faltan variables: '
            + ', '.join(missing)
        )


def _resolve_destination_value(data: dict[str, Any]) -> tuple[str, str]:
    ui_code = (data.get('destination_ui_code') or '').strip()
    siebel_value = (data.get('destination_siebel') or '').strip()

    try:
        if ui_code:
            return ui_code, resolve_destination(ui_code=ui_code)
        if siebel_value:
            return '', resolve_destination(siebel_value=siebel_value)
    except ValueError as exc:
        raise QuoteServiceError(str(exc)) from exc

    raise QuoteServiceError('Se requiere destination_ui_code o destination_siebel')


def _validate_passenger_ages(passenger_count: int, ages: list[int]) -> None:
    if passenger_count < 1 or passenger_count > 10:
        raise QuoteServiceError('passenger_count debe estar entre 1 y 10')
    if len(ages) < 1:
        raise QuoteServiceError('Se requiere al menos una edad de pasajero')
    if len(ages) < passenger_count:
        raise QuoteServiceError(
            f'Se requieren {passenger_count} edades, se recibieron {len(ages)}'
        )
    for age in ages[:passenger_count]:
        if age < 0 or age > 120:
            raise QuoteServiceError(f'Edad inválida: {age}')


def _persist_products(quote: TravelQuote, products_data: list[dict[str, Any]]) -> list[QuoteProduct]:
    quote.products.all().delete()
    created: list[QuoteProduct] = []

    for item in products_data:
        if item.get('error_code') and str(item.get('error_code')) not in ('00', '0', ''):
            continue
        if not item.get('product_id'):
            continue

        prices = item.get('prices') or {}
        product = QuoteProduct.objects.create(
            quote=quote,
            product_id_siebel=item['product_id'],
            product_name=item.get('product_name') or '',
            family=item.get('family') or '',
            category=item.get('category') or '',
            brand=item.get('brand') or '',
            logo=item.get('logo') or '',
            price_emission=_to_decimal(prices.get('emission')),
            price_emission_local=_to_decimal(prices.get('emission_local')),
            price_gross=_to_decimal(prices.get('gross')),
            price_gross_local=_to_decimal(prices.get('gross_local')),
            price_unit=_to_decimal(prices.get('unit')),
            price_net=_to_decimal(prices.get('net')),
            price_net_local=_to_decimal(prices.get('net_local')),
            currency=prices.get('currency') or '',
            currency_local=prices.get('currency_local') or '',
            exchange_rate=_to_decimal(prices.get('exchange_rate')),
            geographic_scope=item.get('geographic_scope') or '',
            age_limit_lower=_to_int(item.get('age_limit_lower')),
            age_limit_upper=_to_int(item.get('age_limit_upper')),
            error_code=item.get('error_code') or '',
            error_message=item.get('error_message') or '',
        )
        for order, attr in enumerate(item.get('coverage_attributes') or []):
            QuoteProductAttribute.objects.create(
                product=product,
                name=attr.get('name') or '',
                visible_name=attr.get('visible_name') or '',
                unit=attr.get('unit') or '',
                value=str(attr.get('value') or ''),
                sort_order=order,
            )
        created.append(product)

    return created


def _no_products_message(
    quote: TravelQuote,
    products_data: list[dict[str, Any]] | None = None,
) -> str:
    if quote.trip_type == 'Varios viajes':
        return (
            'No hay planes disponibles para viajes múltiples en este momento. '
            'Seleccione "Un viaje" para continuar.'
        )

    if products_data:
        for item in products_data:
            error_message = str(item.get('error_message') or '').lower()
            if 'fecha' in error_message and quote.trip_type == 'Varios viajes':
                return (
                    'Universal Assistance no cotiza "Varios viajes" con la '
                    'configuración actual. Use "Un viaje".'
                )

    return (
        'No existen productos para los datos del viaje. '
        'Verifique destino, fechas y edades.'
    )


def _call_ua_quote(
    *,
    quote: TravelQuote,
    quote_count: int,
    actor_user,
    correlation_id: str,
) -> dict[str, Any]:
    _ensure_ua_configured()
    client = LeadCotizadorClient(actor_user=actor_user, correlation_id=correlation_id)
    return client.quote(datos={
        'lead_id': quote.lead_id_siebel,
        'quote_count': quote_count,
        'affiliate_type': quote.affiliate_type,
        'origin_country': quote.origin_country,
        'destination': quote.destination_siebel,
        'trip_type': quote.trip_type,
        'start_date': _format_siebel_date(quote.start_date),
        'end_date': _format_siebel_date(quote.end_date),
        'passenger_count': quote.passenger_count,
        'ages': quote.passenger_ages,
        'category': quote.category,
        'contact_first_name': quote.contact_first_name,
        'contact_last_name': quote.contact_last_name,
        'contact_email': quote.contact_email,
        'contact_phone': quote.contact_phone,
    })


@transaction.atomic
def create_travel_quote(
    *,
    user,
    data: dict[str, Any],
    ip_address: str | None = None,
    correlation_id: str = '',
) -> TravelQuote:
    ui_code, destination_siebel = _resolve_destination_value(data)
    ages = [int(a) for a in data['passenger_ages']]
    passenger_count = int(data['passenger_count'])
    _validate_passenger_ages(passenger_count, ages)

    quote = TravelQuote.objects.create(
        user=user,
        affiliate_type=data.get('affiliate_type', TravelQuote.AffiliateType.INDIVIDUAL),
        origin_country=data.get('origin_country', settings.UA_DEFAULT_ORIGIN_COUNTRY),
        destination_ui_code=ui_code,
        destination_siebel=destination_siebel,
        trip_type=data['trip_type'],
        start_date=data['start_date'],
        end_date=data['end_date'],
        passenger_count=passenger_count,
        passenger_ages=ages[:passenger_count],
        category=data.get('category', ''),
        contact_first_name=data.get('contact_first_name') or (
            user.full_name.split()[0] if user.full_name else ''
        ),
        contact_last_name=data.get('contact_last_name', ''),
        contact_email=data.get('contact_email', user.email_primary),
        contact_phone=data.get('contact_phone', user.phone or ''),
        quote_count=0,
        expires_at=TravelQuote.default_expires_at(),
    )

    try:
        ua_response = _call_ua_quote(
            quote=quote,
            quote_count=0,
            actor_user=user,
            correlation_id=correlation_id,
        )
    except (SiebelSoapError, SiebelBusinessError, IntegrationError) as exc:
        logger.error('UA quote failed on create: %s', exc)
        raise QuoteServiceError(str(exc)) from exc

    quote.lead_id_siebel = ua_response.get('lead_id') or ''
    quote.status = TravelQuote.Status.QUOTED
    quote.save(update_fields=['lead_id_siebel', 'status', 'updated_at'])

    products = _persist_products(quote, ua_response.get('products') or [])
    if not products:
        raise QuoteServiceError(
            _no_products_message(quote, ua_response.get('products'))
        )

    log_audit_event(
        actor_user=user,
        action=QUOTE_CREATED,
        entity='TravelQuote',
        entity_id=quote.id,
        metadata={'lead_id': quote.lead_id_siebel, 'products_count': len(products)},
        ip_address=ip_address,
    )
    return quote


@transaction.atomic
def requote_travel_quote(
    *,
    quote: TravelQuote,
    data: dict[str, Any],
    ip_address: str | None = None,
    correlation_id: str = '',
) -> TravelQuote:
    quote.mark_expired_if_needed()
    if quote.status == TravelQuote.Status.EXPIRED:
        raise QuoteServiceError('La cotización expiró. Cree una nueva cotización.')
    if quote.status == TravelQuote.Status.CONVERTED:
        raise QuoteServiceError('La cotización ya fue convertida.')
    if quote.status == TravelQuote.Status.ASSIGNED:
        raise QuoteServiceError(
            'Esta cotización ya fue enviada al área comercial. '
            'Cree una nueva cotización si necesita recotizar.'
        )
    if not quote.lead_id_siebel:
        raise QuoteServiceError('La cotización no tiene lead de Siebel para recotizar.')

    if 'destination_ui_code' in data or 'destination_siebel' in data:
        ui_code, destination_siebel = _resolve_destination_value(data)
        quote.destination_ui_code = ui_code
        quote.destination_siebel = destination_siebel

    for field in (
        'affiliate_type', 'origin_country', 'trip_type', 'start_date',
        'end_date', 'category', 'contact_first_name', 'contact_last_name',
        'contact_email', 'contact_phone',
    ):
        if field in data and data[field] is not None:
            setattr(quote, field, data[field])

    if 'passenger_count' in data:
        quote.passenger_count = int(data['passenger_count'])
    if 'passenger_ages' in data:
        quote.passenger_ages = [int(a) for a in data['passenger_ages']]

    _validate_passenger_ages(quote.passenger_count, quote.passenger_ages)

    new_count = quote.quote_count + 1
    quote.selected_product = None

    try:
        ua_response = _call_ua_quote(
            quote=quote,
            quote_count=new_count,
            actor_user=quote.user,
            correlation_id=correlation_id,
        )
    except (SiebelSoapError, SiebelBusinessError, IntegrationError) as exc:
        raise QuoteServiceError(str(exc)) from exc

    quote.quote_count = new_count
    quote.lead_id_siebel = ua_response.get('lead_id') or quote.lead_id_siebel
    quote.status = TravelQuote.Status.QUOTED
    quote.expires_at = TravelQuote.default_expires_at()
    quote.save()

    products = _persist_products(quote, ua_response.get('products') or [])
    if not products:
        raise QuoteServiceError(
            _no_products_message(quote, ua_response.get('products'))
        )

    log_audit_event(
        actor_user=quote.user,
        action=QUOTE_REQUOTED,
        entity='TravelQuote',
        entity_id=quote.id,
        metadata={'lead_id': quote.lead_id_siebel, 'quote_count': quote.quote_count},
        ip_address=ip_address,
    )
    return quote


@transaction.atomic
def select_quote_product(
    *,
    quote: TravelQuote,
    product_id: UUID,
    ip_address: str | None = None,
) -> TravelQuote:
    quote.mark_expired_if_needed()
    if quote.is_expired:
        raise QuoteServiceError('La cotización expiró. Genera una nueva cotización.')
    if quote.status == TravelQuote.Status.CONVERTED:
        raise QuoteServiceError('La cotización ya fue convertida.')
    if quote.status == TravelQuote.Status.ASSIGNED:
        raise QuoteServiceError(
            'Esta cotización ya fue seleccionada y enviada al área comercial.'
        )

    try:
        product = quote.products.get(id=product_id)
    except QuoteProduct.DoesNotExist as exc:
        raise QuoteServiceError('Producto no encontrado en esta cotización.') from exc

    quote.selected_product = product
    quote.status = TravelQuote.Status.SELECTED
    quote.selected_at = timezone.now()
    quote.save(update_fields=['selected_product', 'status', 'selected_at', 'updated_at'])

    log_audit_event(
        actor_user=quote.user,
        action=QUOTE_PRODUCT_SELECTED,
        entity='TravelQuote',
        entity_id=quote.id,
        metadata={
            'product_id_siebel': product.product_id_siebel,
            'product_name': product.product_name,
        },
        ip_address=ip_address,
    )

    # Flujo comercial: guardar selección, asignar ejecutivo y notificar (sin pago/emisión).
    return assign_commercial_for_quote(quote=quote, ip_address=ip_address)


def get_user_quote(*, user, quote_id: UUID) -> TravelQuote:
    try:
        quote = TravelQuote.objects.select_related('selected_product', 'user').prefetch_related(
            'products__attributes', 'passengers',
        ).get(id=quote_id, user=user)
    except TravelQuote.DoesNotExist as exc:
        raise QuoteServiceError('Cotización no encontrada.') from exc
    quote.mark_expired_if_needed()
    return quote


def list_user_quotes(*, user, include_expired: bool = False):
    qs = TravelQuote.objects.filter(user=user).select_related('selected_product').prefetch_related(
        'products', 'passengers',
    )
    if not include_expired:
        qs = qs.exclude(status=TravelQuote.Status.EXPIRED).filter(
            expires_at__gt=timezone.now(),
        )
    for quote in qs:
        quote.mark_expired_if_needed()
    return qs.order_by('-created_at')


@transaction.atomic
def save_quote_passengers(
    *,
    quote: TravelQuote,
    passengers_data: list[dict],
    ip_address: str | None = None,
) -> TravelQuote:
    quote.mark_expired_if_needed()
    if quote.is_expired:
        raise QuoteServiceError('La cotización expiró.')
    if quote.status != TravelQuote.Status.SELECTED and quote.status != TravelQuote.Status.ASSIGNED:
        raise QuoteServiceError(
            'Debe seleccionar un plan antes de registrar pasajeros.'
        )
    if len(passengers_data) < quote.passenger_count:
        raise QuoteServiceError(
            f'Se requieren {quote.passenger_count} pasajeros.'
        )

    quote.passengers.all().delete()
    for order, item in enumerate(passengers_data[:quote.passenger_count]):
        QuotePassenger.objects.create(
            quote=quote,
            sort_order=order,
            first_name=item['first_name'],
            last_name=item['last_name'],
            document_type=item['document_type'],
            document_number=item['document_number'],
            birth_date=item['birth_date'],
            email=item.get('email') or quote.contact_email,
            phone=item.get('phone') or quote.contact_phone,
            residence_country=item.get('residence_country') or quote.origin_country,
            city=item.get('city') or '',
        )

    log_audit_event(
        actor_user=quote.user,
        action=QUOTE_PASSENGERS_SAVED,
        entity='TravelQuote',
        entity_id=quote.id,
        metadata={'passengers_count': len(passengers_data)},
        ip_address=ip_address,
    )
    return quote
