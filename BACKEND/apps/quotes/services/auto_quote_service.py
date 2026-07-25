"""Business logic for Allianz autos quotes (Call4 individual)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.constants import QUOTE_CREATED, QUOTE_PRODUCT_SELECTED
from apps.audit.services.audit_log import log_audit_event
from apps.integrations.clients import AllianzAutosClient
from apps.integrations.exceptions import IntegrationError, SiebelBusinessError, SiebelSoapError
from apps.quotes.models import AutoQuote, AutoQuoteCoverage, AutoQuotePackage
from apps.quotes.services.commercial_assignment import assign_commercial_for_quote

logger = logging.getLogger(__name__)


class AutoQuoteServiceError(Exception):
    """Raised when auto quote operations fail validation or integration."""


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _format_allianz_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime('%Y%m%d')
    if isinstance(value, str):
        for fmt in ('%Y-%m-%d', '%Y%m%d', '%d/%m/%Y'):
            try:
                return datetime.strptime(value, fmt).strftime('%Y%m%d')
            except ValueError:
                continue
    raise AutoQuoteServiceError(f'Fecha inválida: {value}')


def _yn(value: bool | str | None, default: str = 'N') -> str:
    if isinstance(value, bool):
        return 'S' if value else 'N'
    if value is None:
        return default
    raw = str(value).strip().upper()
    if raw in ('S', 'SI', 'YES', 'TRUE', '1', 'Y'):
        return 'S'
    if raw in ('N', 'NO', 'FALSE', '0'):
        return 'N'
    return default


def _normalize_plate(plate: str) -> str:
    cleaned = ''.join(ch for ch in (plate or '').upper() if ch.isalnum())
    if len(cleaned) < 5 or len(cleaned) > 8:
        raise AutoQuoteServiceError('La placa del vehículo no es válida.')
    return cleaned


def _normalize_sex(sex: str) -> str:
    raw = (sex or 'M').strip().upper()
    if raw in ('M', 'MASCULINO', 'HOMBRE', 'H'):
        return 'M'
    if raw in ('F', 'FEMENINO', 'MUJER'):
        return 'F'
    raise AutoQuoteServiceError('Sexo inválido. Use M o F.')


def _normalize_doc_type(doc_type: str) -> str:
    raw = (doc_type or 'C').strip().upper()
    mapping = {
        'C': 'C',
        'CC': 'C',
        'CEDULA': 'C',
        'CÉDULA': 'C',
        'N': 'N',
        'NIT': 'N',
        'E': 'E',
        'CE': 'E',
        'EXTRANJERIA': 'E',
        'EXTRANJERÍA': 'E',
    }
    if raw not in mapping:
        raise AutoQuoteServiceError('Tipo de documento inválido.')
    return mapping[raw]


def _persist_packages(quote: AutoQuote, packages_data: list[dict[str, Any]]) -> list[AutoQuotePackage]:
    quote.products.all().delete()
    created: list[AutoQuotePackage] = []

    for item in packages_data:
        package_id = str(item.get('package_id') or item.get('product_id') or '').strip()
        if not package_id:
            continue
        prices = item.get('prices') or {}
        payments = item.get('payments') or {}
        annual = _to_decimal(payments.get('annual')) or _to_decimal(prices.get('emission_local'))
        monthly = _to_decimal(payments.get('monthly')) or _to_decimal(prices.get('unit'))

        product = AutoQuotePackage.objects.create(
            quote=quote,
            package_id=package_id,
            product_id_siebel=package_id,
            product_name=item.get('product_name') or item.get('package_name') or f'Paquete {package_id}',
            brand=item.get('brand') or 'Allianz',
            logo=item.get('logo') or 'allianz',
            price_emission=_to_decimal(prices.get('emission')) or annual,
            price_emission_local=_to_decimal(prices.get('emission_local')) or annual,
            price_gross=_to_decimal(prices.get('gross')) or annual,
            price_gross_local=_to_decimal(prices.get('gross_local')) or annual,
            price_unit=monthly,
            price_net=_to_decimal(prices.get('net')) or annual,
            price_net_local=_to_decimal(prices.get('net_local')) or annual,
            premium_annual=annual,
            premium_monthly=monthly,
            premium_semestral=_to_decimal(payments.get('semestral')),
            premium_trimestral=_to_decimal(payments.get('trimestral')),
            currency=prices.get('currency') or 'COP',
            currency_local=prices.get('currency_local') or 'COP',
        )
        for order, cov in enumerate(item.get('coverages') or []):
            name = cov.get('name') or ''
            insured = str(cov.get('insured_value') or '')
            deductible = str(cov.get('deductible') or '')
            AutoQuoteCoverage.objects.create(
                product=product,
                coverage_id=str(cov.get('coverage_id') or ''),
                name=name,
                visible_name=name,
                unit='COP',
                value=insured,
                deductible=deductible,
                sort_order=order,
            )
        created.append(product)

    return created


def _build_allianz_payload(quote: AutoQuote) -> dict[str, Any]:
    return {
        'transaction_number': f'CASSE{timezone.now().strftime("%H%M%S")}',
        'product_code': quote.product_code or settings.ALLIANZ_PRODUCT_CODE,
        'effective_date': _format_allianz_date(quote.effective_date),
        'term_date': _format_allianz_date(quote.term_date),
        'holder_doc_type': quote.holder_doc_type,
        'holder_doc_number': quote.holder_doc_number,
        'owner_doc_type': quote.holder_doc_type,
        'owner_doc_number': quote.holder_doc_number,
        'is_holder_driver': _yn(quote.is_holder_driver, 'S'),
        'is_holder_owner': _yn(quote.is_holder_owner, 'S'),
        'is_new_owner': 'S',
        'risk_type': quote.risk_type or settings.ALLIANZ_DEFAULT_RISK_TYPE,
        'vehicle_plate': quote.vehicle_plate,
        'fasecolda_code': quote.fasecolda_code or None,
        'vehicle_year': quote.vehicle_year,
        'owner_born_date': _format_allianz_date(quote.holder_born_date),
        'owner_sex': quote.holder_sex,
        'is_new_vehicle': _yn(quote.is_new_vehicle, 'N'),
        'insured_value': str(quote.insured_value or 0),
        'circulation_dane_code': quote.circulation_dane_code or '11001',
        'cap': settings.ALLIANZ_CAP,
    }


def _call_allianz(*, quote: AutoQuote, actor_user, correlation_id: str) -> dict[str, Any]:
    client = AllianzAutosClient(actor_user=actor_user, correlation_id=correlation_id)
    try:
        return client.quote(_build_allianz_payload(quote))
    finally:
        client.close()


@transaction.atomic
def create_auto_quote(
    *,
    user,
    data: dict[str, Any],
    ip_address: str | None = None,
    correlation_id: str = '',
) -> AutoQuote:
    plate = _normalize_plate(data['vehicle_plate'])
    effective = data.get('effective_date') or timezone.localdate()
    if isinstance(effective, str):
        effective = datetime.strptime(effective, '%Y-%m-%d').date()
    term = data.get('term_date') or (effective + timedelta(days=365))
    if isinstance(term, str):
        term = datetime.strptime(term, '%Y-%m-%d').date()
    if term <= effective:
        raise AutoQuoteServiceError('term_date debe ser posterior a effective_date.')

    born = data['holder_born_date']
    if isinstance(born, str):
        born = datetime.strptime(born, '%Y-%m-%d').date()

    quote = AutoQuote.objects.create(
        user=user,
        affiliate_type=data.get('affiliate_type', AutoQuote.AffiliateType.INDIVIDUAL),
        product_code=data.get('product_code') or settings.ALLIANZ_PRODUCT_CODE,
        vehicle_plate=plate,
        vehicle_year=data.get('vehicle_year'),
        fasecolda_code=(data.get('fasecolda_code') or '').strip(),
        risk_type=data.get('risk_type') or settings.ALLIANZ_DEFAULT_RISK_TYPE,
        is_new_vehicle=bool(data.get('is_new_vehicle', False)),
        in_dealership=bool(data.get('in_dealership', False)),
        insured_value=_to_decimal(data.get('insured_value')) or Decimal('0'),
        circulation_dane_code=(data.get('circulation_dane_code') or '11001').strip(),
        circulation_city_name=(data.get('circulation_city_name') or '').strip(),
        holder_doc_type=_normalize_doc_type(data.get('holder_doc_type', 'C')),
        holder_doc_number=str(data['holder_doc_number']).strip(),
        holder_born_date=born,
        holder_sex=_normalize_sex(data.get('holder_sex', 'M')),
        is_holder_driver=bool(data.get('is_holder_driver', True)),
        is_holder_owner=bool(data.get('is_holder_owner', True)),
        effective_date=effective,
        term_date=term,
        contact_first_name=data.get('contact_first_name') or (
            user.full_name.split()[0] if getattr(user, 'full_name', None) else ''
        ),
        contact_last_name=data.get('contact_last_name', ''),
        contact_email=data.get('contact_email') or getattr(user, 'email_primary', ''),
        contact_phone=data.get('contact_phone') or getattr(user, 'phone', '') or '',
        expires_at=AutoQuote.default_expires_at(),
    )

    try:
        response = _call_allianz(
            quote=quote,
            actor_user=user,
            correlation_id=correlation_id,
        )
    except (SiebelSoapError, SiebelBusinessError, IntegrationError) as exc:
        logger.error('Allianz auto quote failed: %s', exc)
        raise AutoQuoteServiceError(str(exc)) from exc

    vehicle = response.get('vehicle_details') or {}
    quote.allianz_quotation_number = response.get('quotation_number') or ''
    quote.vehicle_brand = vehicle.get('brand') or ''
    quote.vehicle_line = vehicle.get('type') or ''
    quote.vehicle_version = vehicle.get('version') or ''
    if vehicle.get('year') and not quote.vehicle_year:
        try:
            quote.vehicle_year = int(str(vehicle['year'])[:4])
        except (TypeError, ValueError):
            pass
    quote.status = AutoQuote.Status.QUOTED
    quote.save()

    products = _persist_packages(quote, response.get('packages') or [])
    if not products:
        raise AutoQuoteServiceError(
            'No existen paquetes Allianz para los datos del vehículo. '
            'Verifique placa, documento y ciudad de circulación.'
        )

    log_audit_event(
        actor_user=user,
        action=QUOTE_CREATED,
        entity='AutoQuote',
        entity_id=quote.id,
        metadata={
            'quotation_number': quote.allianz_quotation_number,
            'products_count': len(products),
            'plate': quote.vehicle_plate,
            'mock': bool(getattr(settings, 'ALLIANZ_MOCK', False)),
        },
        ip_address=ip_address,
    )
    return quote


@transaction.atomic
def select_auto_quote_product(
    *,
    quote: AutoQuote,
    product_id: UUID,
    ip_address: str | None = None,
) -> AutoQuote:
    quote.mark_expired_if_needed()
    if quote.is_expired:
        raise AutoQuoteServiceError('La cotización expiró. Genera una nueva cotización.')
    if quote.status == AutoQuote.Status.CONVERTED:
        raise AutoQuoteServiceError('La cotización ya fue convertida.')
    if quote.status == AutoQuote.Status.ASSIGNED:
        raise AutoQuoteServiceError(
            'Esta cotización ya fue seleccionada y enviada al área comercial.'
        )

    try:
        product = quote.products.get(id=product_id)
    except AutoQuotePackage.DoesNotExist as exc:
        raise AutoQuoteServiceError('Paquete no encontrado en esta cotización.') from exc

    quote.selected_product = product
    quote.status = AutoQuote.Status.SELECTED
    quote.selected_at = timezone.now()
    quote.save(update_fields=['selected_product', 'status', 'selected_at', 'updated_at'])

    log_audit_event(
        actor_user=quote.user,
        action=QUOTE_PRODUCT_SELECTED,
        entity='AutoQuote',
        entity_id=quote.id,
        metadata={
            'package_id': product.package_id,
            'product_name': product.product_name,
        },
        ip_address=ip_address,
    )
    return assign_commercial_for_quote(quote=quote, ip_address=ip_address)


def get_user_auto_quote(*, user, quote_id: UUID) -> AutoQuote:
    try:
        quote = AutoQuote.objects.select_related('selected_product', 'user').prefetch_related(
            'products__attributes',
        ).get(id=quote_id, user=user)
    except AutoQuote.DoesNotExist as exc:
        raise AutoQuoteServiceError('Cotización no encontrada.') from exc
    quote.mark_expired_if_needed()
    return quote


def list_user_auto_quotes(*, user, include_expired: bool = False):
    qs = AutoQuote.objects.filter(user=user).select_related('selected_product').prefetch_related(
        'products',
    )
    if not include_expired:
        qs = qs.exclude(status=AutoQuote.Status.EXPIRED).filter(
            expires_at__gt=timezone.now(),
        )
    for quote in qs:
        quote.mark_expired_if_needed()
    return qs.order_by('-created_at')
