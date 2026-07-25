"""Business logic for Allianz Hogar Individual quotes (product 2013)."""
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
from apps.integrations.clients import AllianzHogarClient
from apps.integrations.exceptions import IntegrationError, SiebelBusinessError, SiebelSoapError
from apps.quotes.models import HomeQuote, HomeQuoteCoverage, HomeQuotePackage
from apps.quotes.services.commercial_assignment import assign_commercial_for_quote

logger = logging.getLogger(__name__)


class HomeQuoteServiceError(Exception):
    """Raised when home quote operations fail validation or integration."""


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _yn(value: bool | str | None, default: str = 'S') -> str:
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


def _normalize_doc_type(doc_type: str) -> str:
    raw = (doc_type or 'C').strip().upper()
    mapping = {
        'C': 'C', 'CC': 'C', 'CEDULA': 'C', 'CÉDULA': 'C',
        'N': 'N', 'NIT': 'N',
        'E': 'X', 'CE': 'X', 'X': 'X', 'EXTRANJERIA': 'X', 'EXTRANJERÍA': 'X',
        'P': 'P', 'PASAPORTE': 'P',
    }
    if raw not in mapping:
        raise HomeQuoteServiceError('Tipo de documento inválido.')
    return mapping[raw]


def _validate_risk_values(data: dict[str, Any]) -> None:
    category = str(data.get('risk_category') or '3')
    building = _to_decimal(data.get('building_value')) or Decimal('0')
    contents = _to_decimal(data.get('contents_value')) or Decimal('0')
    theft = _to_decimal(data.get('theft_value')) or Decimal('0')
    all_risk = _to_decimal(data.get('all_risk_value')) or Decimal('0')

    if building <= 0 and contents <= 0:
        raise HomeQuoteServiceError(
            'Debe seleccionar algún valor para Edificio y/o Contenido.'
        )
    if building >= Decimal('3000000000') or contents >= Decimal('3000000000'):
        raise HomeQuoteServiceError(
            'Valor asegurado fuera del rango permitido, contacte su unidad comercial.'
        )
    if category == '1' and building <= 0:
        raise HomeQuoteServiceError(
            'Para propietario que arrienda debe enviar el valor del edificio.'
        )
    if category == '2':
        if building > 0:
            raise HomeQuoteServiceError(
                'Para inquilino no se permite valor de edificio.'
            )
        if contents <= 0:
            raise HomeQuoteServiceError(
                'Para inquilino debe seleccionar valor de contenido.'
            )
    if category == '3' and building <= 0:
        raise HomeQuoteServiceError(
            'Para propietario que habita debe enviar el valor del edificio.'
        )
    if (theft > 0 or all_risk > 0) and contents <= 0 and category != '1':
        raise HomeQuoteServiceError(
            'Debe seleccionar valor de contenido para hurto o todo riesgo.'
        )
    if all_risk > 0 and theft <= 0 and category in ('2', '3'):
        raise HomeQuoteServiceError(
            'Si selecciona Todo riesgo es obligatorio seleccionar un valor en Hurto.'
        )


def _persist_packages(quote: HomeQuote, packages_data: list[dict[str, Any]]) -> list[HomeQuotePackage]:
    quote.products.all().delete()
    created: list[HomeQuotePackage] = []
    for item in packages_data:
        package_id = str(item.get('package_id') or item.get('product_id') or '').strip()
        if not package_id:
            continue
        prices = item.get('prices') or {}
        payments = item.get('payments') or {}
        annual = _to_decimal(payments.get('annual')) or _to_decimal(prices.get('emission_local'))
        monthly = _to_decimal(payments.get('monthly')) or _to_decimal(prices.get('unit'))
        product = HomeQuotePackage.objects.create(
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
        for idx, cov in enumerate(item.get('coverages') or []):
            HomeQuoteCoverage.objects.create(
                product=product,
                coverage_id=str(cov.get('coverage_id') or ''),
                name=cov.get('name') or '',
                visible_name=cov.get('name') or '',
                value=str(cov.get('insured_value') or ''),
                deductible=str(cov.get('deductible') or ''),
                sort_order=idx,
            )
        created.append(product)
    return created


def _call_allianz(*, quote: HomeQuote, actor_user, correlation_id: str) -> dict[str, Any]:
    client = AllianzHogarClient(actor_user=actor_user, correlation_id=correlation_id)
    try:
        payload = {
            'product_code': quote.product_code,
            'effective_date': quote.effective_date.strftime('%Y%m%d'),
            'payment_frequency': quote.payment_frequency,
            'holder_doc_type': quote.holder_doc_type,
            'holder_doc_number': quote.holder_doc_number,
            'is_holder_owner': _yn(quote.is_holder_owner),
            'risk_category': quote.risk_category,
            'locality_dane_code': quote.locality_dane_code,
            'address': quote.address,
            'address_extra': quote.address_extra,
            'building_value': quote.building_value,
            'contents_value': quote.contents_value,
            'theft_value': quote.theft_value,
            'all_risk_value': quote.all_risk_value,
            'pet_coverage': quote.pet_coverage,
            'construction_year': quote.construction_year,
            'total_floors': quote.total_floors,
            'apartment_floor': quote.apartment_floor,
            'basements': quote.basements,
            'area_sqm': quote.area_sqm,
            'construction_type': quote.construction_type,
            'housing_type': quote.housing_type,
            'transaction_number': f'CASSE-{quote.id.hex[:10].upper()}',
        }
        return client.quote(payload)
    finally:
        client.close()


@transaction.atomic
def create_home_quote(
    *,
    user,
    data: dict[str, Any],
    ip_address: str | None = None,
    correlation_id: str = '',
) -> HomeQuote:
    _validate_risk_values(data)

    effective = data.get('effective_date') or timezone.localdate()
    if isinstance(effective, str):
        effective = datetime.strptime(effective, '%Y-%m-%d').date()
    term = data.get('term_date') or (effective + timedelta(days=365))
    if isinstance(term, str):
        term = datetime.strptime(term, '%Y-%m-%d').date()
    if term <= effective:
        raise HomeQuoteServiceError('term_date debe ser posterior a effective_date.')

    address = (data.get('address') or '').strip()
    if len(address) < 5:
        raise HomeQuoteServiceError('La dirección del inmueble es obligatoria.')

    quote = HomeQuote.objects.create(
        user=user,
        affiliate_type=data.get('affiliate_type', HomeQuote.AffiliateType.INDIVIDUAL),
        affiliation_number=(data.get('affiliation_number') or '').strip(),
        payment_form=(data.get('payment_form') or '').strip(),
        paying_company=(data.get('paying_company') or '').strip(),
        product_code=data.get('product_code') or settings.ALLIANZ_HOGAR_PRODUCT_CODE,
        risk_category=str(data.get('risk_category') or '3'),
        locality_dane_code=(data.get('locality_dane_code') or '11001').strip(),
        city_name=(data.get('city_name') or '').strip(),
        address=address[:120],
        address_extra=(data.get('address_extra') or '').strip()[:120],
        building_value=_to_decimal(data.get('building_value')) or Decimal('0'),
        contents_value=_to_decimal(data.get('contents_value')) or Decimal('0'),
        theft_value=_to_decimal(data.get('theft_value')) or Decimal('0'),
        all_risk_value=_to_decimal(data.get('all_risk_value')) or Decimal('0'),
        pet_coverage=(data.get('pet_coverage') or 'NO').strip().upper()[:4],
        construction_year=int(data['construction_year']),
        total_floors=int(data.get('total_floors') or 1),
        apartment_floor=int(data.get('apartment_floor') or 1),
        basements=int(data.get('basements') or 0),
        area_sqm=int(data.get('area_sqm') or 50),
        construction_type=str(data.get('construction_type') or '3'),
        housing_type=str(data.get('housing_type') or '2'),
        payment_frequency=str(data.get('payment_frequency') or 'A')[:1],
        holder_doc_type=_normalize_doc_type(data.get('holder_doc_type', 'C')),
        holder_doc_number=str(data['holder_doc_number']).strip(),
        is_holder_owner=bool(data.get('is_holder_owner', True)),
        effective_date=effective,
        term_date=term,
        contact_first_name=data.get('contact_first_name') or (
            user.full_name.split()[0] if getattr(user, 'full_name', None) else ''
        ),
        contact_last_name=data.get('contact_last_name', ''),
        contact_email=data.get('contact_email') or getattr(user, 'email_primary', ''),
        contact_phone=data.get('contact_phone') or getattr(user, 'phone', '') or '',
        expires_at=HomeQuote.default_expires_at(),
    )

    try:
        response = _call_allianz(
            quote=quote,
            actor_user=user,
            correlation_id=correlation_id,
        )
    except (SiebelSoapError, SiebelBusinessError, IntegrationError) as exc:
        logger.error('Allianz home quote failed: %s', exc)
        raise HomeQuoteServiceError(str(exc)) from exc

    quote.allianz_quotation_number = response.get('quotation_number') or ''
    quote.risk_type_desc = response.get('risk_type_desc') or ''
    if response.get('city') and not quote.city_name:
        quote.city_name = response['city']
    quote.status = HomeQuote.Status.QUOTED
    quote.save()

    products = _persist_packages(quote, response.get('packages') or [])
    if not products:
        raise HomeQuoteServiceError(
            'No existen paquetes Allianz Hogar para los datos del inmueble.'
        )

    log_audit_event(
        actor_user=user,
        action=QUOTE_CREATED,
        entity='HomeQuote',
        entity_id=quote.id,
        metadata={
            'quotation_number': quote.allianz_quotation_number,
            'products_count': len(products),
            'address': quote.address,
            'mock': bool(getattr(settings, 'ALLIANZ_HOGAR_MOCK', False)),
        },
        ip_address=ip_address,
    )
    return quote


def list_user_home_quotes(*, user, include_expired: bool = False):
    qs = HomeQuote.objects.filter(user=user).prefetch_related('products')
    if not include_expired:
        qs = qs.exclude(status=HomeQuote.Status.EXPIRED)
    quotes = list(qs)
    for quote in quotes:
        quote.mark_expired_if_needed()
    if not include_expired:
        quotes = [q for q in quotes if q.status != HomeQuote.Status.EXPIRED]
    return quotes


def get_user_home_quote(*, user, quote_id: UUID) -> HomeQuote:
    try:
        quote = HomeQuote.objects.prefetch_related(
            'products__attributes',
        ).get(id=quote_id, user=user)
    except HomeQuote.DoesNotExist as exc:
        raise HomeQuoteServiceError('Cotización de hogar no encontrada.') from exc
    quote.mark_expired_if_needed()
    return quote


@transaction.atomic
def select_home_quote_product(
    *,
    quote: HomeQuote,
    product_id: UUID,
    ip_address: str | None = None,
) -> HomeQuote:
    if quote.status == HomeQuote.Status.EXPIRED or quote.is_expired:
        raise HomeQuoteServiceError('La cotización expiró. Genera una nueva.')
    try:
        product = quote.products.get(id=product_id)
    except HomeQuotePackage.DoesNotExist as exc:
        raise HomeQuoteServiceError('Paquete no encontrado en esta cotización.') from exc

    quote.selected_product = product
    quote.selected_at = timezone.now()
    quote.status = HomeQuote.Status.SELECTED
    quote.save(update_fields=['selected_product', 'selected_at', 'status', 'updated_at'])

    log_audit_event(
        actor_user=quote.user,
        action=QUOTE_PRODUCT_SELECTED,
        entity='HomeQuote',
        entity_id=quote.id,
        metadata={'product_id': str(product.id), 'package_id': product.package_id},
        ip_address=ip_address,
    )
    return assign_commercial_for_quote(quote=quote, ip_address=ip_address)
