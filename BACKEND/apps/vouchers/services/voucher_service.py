"""Voucher issuance orchestration (Alta → Portal → PDF → Retire lead)."""
from __future__ import annotations

import base64
import logging
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.constants import VOUCHER_ISSUE_FAILED, VOUCHER_ISSUED
from apps.audit.services.audit_log import log_audit_event
from apps.integrations.clients import (
    LeadServiceClient,
    QueryVoucherPortalClient,
    SendReportClient,
    VoucherClient,
)
from apps.integrations.exceptions import IntegrationError, SiebelBusinessError, SiebelSoapError
from apps.payments.models import Payment
from apps.quotes.models import TravelQuote
from apps.vouchers.models import TravelVoucher

logger = logging.getLogger(__name__)


class VoucherServiceError(Exception):
    """Raised when voucher operations fail."""


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
    raise VoucherServiceError(f'Fecha inválida: {value}')


def _control_number_for_quote(quote: TravelQuote) -> str:
    prefix = settings.UA_CONTROL_NUMBER_PREFIX
    return f'{prefix}-{quote.id}'


def _convenio_for_quote(quote: TravelQuote) -> str:
    if quote.affiliate_type == TravelQuote.AffiliateType.CAVIPETROL:
        return settings.UA_CONVENIO_CAVIPETROL_ID
    return settings.UA_CONVENIO_INDIVIDUAL_ID


def _build_voucher_payload(quote: TravelQuote, control_number: str) -> dict:
    product = quote.selected_product
    if not product:
        raise VoucherServiceError('Producto seleccionado no encontrado.')

    applicants = []
    for passenger in quote.passengers.order_by('sort_order'):
        applicants.append({
            'document_type': passenger.document_type,
            'document_number': passenger.document_number,
            'first_name': passenger.first_name,
            'last_name': passenger.last_name,
            'birth_date': _format_siebel_date(passenger.birth_date),
            'residence_country': passenger.residence_country or quote.origin_country,
            'email': passenger.email or quote.contact_email,
            'phone': passenger.phone or quote.contact_phone,
            'city': passenger.city,
        })

    price = product.price_emission or product.price_emission_local
    return {
        'control_number': control_number,
        'price': price,
        'price_emission': product.price_emission or price,
        'currency': product.currency or product.currency_local or 'USD',
        'issue_date': _format_siebel_date(timezone.localdate()),
        'start_date': _format_siebel_date(quote.start_date),
        'end_date': _format_siebel_date(quote.end_date),
        'destination': quote.destination_siebel,
        'lead_id': quote.lead_id_siebel,
        'product_name': product.product_name,
        'contract_id': _convenio_for_quote(quote),
        'send_email': 'N',
        'post_process': 'Y',
        'applicants': applicants,
    }


def _save_pdf(voucher: TravelVoucher, pdf_data: str | bytes) -> str:
    media_root = Path(settings.MEDIA_ROOT)
    target_dir = media_root / 'vouchers'
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f'{voucher.id}.pdf'
    target_path = target_dir / filename

    if isinstance(pdf_data, bytes):
        content = pdf_data
    elif isinstance(pdf_data, str) and pdf_data.startswith('%PDF'):
        content = pdf_data.encode('latin-1')
    else:
        try:
            content = base64.b64decode(pdf_data)
        except Exception:
            content = pdf_data.encode('latin-1')

    target_path.write_bytes(content)
    relative = f'vouchers/{filename}'
    voucher.pdf_path = relative
    voucher.save(update_fields=['pdf_path', 'updated_at'])
    return relative


def _validate_issue_preconditions(quote: TravelQuote, payment: Payment) -> None:
    quote.mark_expired_if_needed()
    if quote.is_expired:
        raise VoucherServiceError('La cotización expiró.')
    if quote.status not in (TravelQuote.Status.SELECTED, TravelQuote.Status.CONVERTED):
        raise VoucherServiceError('La cotización debe tener un plan seleccionado.')
    if not quote.selected_product:
        raise VoucherServiceError('No hay producto seleccionado.')
    if not quote.lead_id_siebel:
        raise VoucherServiceError('La cotización no tiene lead de Siebel.')
    if quote.passengers.count() < quote.passenger_count:
        raise VoucherServiceError(
            f'Se requieren {quote.passenger_count} pasajeros registrados.'
        )
    if payment.quote_id != quote.id:
        raise VoucherServiceError('El pago no corresponde a esta cotización.')
    if payment.status != Payment.Status.COMPLETED:
        raise VoucherServiceError('El pago no está completado.')


def issue_travel_voucher(
    *,
    user,
    quote: TravelQuote,
    payment: Payment,
    ip_address: str | None = None,
    correlation_id: str = '',
) -> TravelVoucher:
    _validate_issue_preconditions(quote, payment)

    existing = TravelVoucher.objects.filter(quote=quote).first()
    if existing and existing.status == TravelVoucher.Status.ISSUED:
        return existing

    control_number = _control_number_for_quote(quote)
    voucher = existing or TravelVoucher.objects.create(
        user=user,
        quote=quote,
        payment=payment,
        control_number=control_number,
        status=TravelVoucher.Status.ISSUING,
    )
    voucher.status = TravelVoucher.Status.ISSUING
    voucher.payment = payment
    voucher.save(update_fields=['status', 'payment', 'updated_at'])

    try:
        payload = _build_voucher_payload(quote, control_number)
        alta_client = VoucherClient(actor_user=user, correlation_id=correlation_id)
        alta_result = alta_client.issue(voucher_data=payload)
        voucher.raw_alta_response = alta_result.get('raw') or {}

        error_code = alta_result.get('error_code')
        if error_code and str(error_code) not in ('00', '0', ''):
            msg = alta_result.get('error_message') or 'Error en Alta de voucher'
            raise VoucherServiceError(f'{msg} (código {error_code})')

        voucher_number = alta_result.get('voucher_number')
        if not voucher_number:
            raise VoucherServiceError('Siebel no devolvió número de voucher.')

        voucher.voucher_number_siebel = voucher_number
        voucher.control_number = alta_result.get('control_number') or control_number

        portal_client = QueryVoucherPortalClient(actor_user=user, correlation_id=correlation_id)
        portal_result = portal_client.query(
            voucher_number=voucher_number,
            organization=settings.UA_ORGANIZATION_ID,
        )
        voucher.raw_portal_response = portal_result if isinstance(portal_result, dict) else {}

        report_client = SendReportClient(actor_user=user, correlation_id=correlation_id)
        report_result = report_client.get_report(
            voucher_number=voucher_number,
            organization=settings.UA_ORGANIZATION_ID,
        )
        voucher.raw_report_response = report_result.get('raw') or {}

        pdf_data = report_result.get('pdf_base64')
        if not pdf_data:
            raise VoucherServiceError('No se pudo obtener el PDF del voucher.')

        _save_pdf(voucher, pdf_data)

        if quote.lead_id_siebel:
            lead_client = LeadServiceClient(actor_user=user, correlation_id=correlation_id)
            lead_client.retire_lead(
                lead_id=quote.lead_id_siebel,
                reason_code=settings.UA_LEAD_RETIRE_REASON_CODE,
                comments='Voucher emitido vía CASSE App',
            )

        voucher.status = TravelVoucher.Status.ISSUED
        voucher.issued_at = timezone.now()
        voucher.error_code = ''
        voucher.error_message = ''
        voucher.save()

        quote.status = TravelQuote.Status.CONVERTED
        quote.save(update_fields=['status', 'updated_at'])

        log_audit_event(
            actor_user=user,
            action=VOUCHER_ISSUED,
            entity='TravelVoucher',
            entity_id=voucher.id,
            metadata={
                'quote_id': str(quote.id),
                'voucher_number': voucher_number,
            },
            ip_address=ip_address,
        )
        return voucher

    except (VoucherServiceError, SiebelSoapError, SiebelBusinessError, IntegrationError) as exc:
        voucher.status = TravelVoucher.Status.ERROR
        voucher.error_message = str(exc)
        voucher.save(update_fields=['status', 'error_message', 'updated_at'])
        log_audit_event(
            actor_user=user,
            action=VOUCHER_ISSUE_FAILED,
            entity='TravelVoucher',
            entity_id=voucher.id,
            metadata={'quote_id': str(quote.id), 'error': str(exc)},
            ip_address=ip_address,
        )
        raise VoucherServiceError(str(exc)) from exc


def get_user_voucher(*, user, voucher_id) -> TravelVoucher:
    try:
        return TravelVoucher.objects.select_related('quote', 'payment').get(
            id=voucher_id,
            user=user,
        )
    except TravelVoucher.DoesNotExist as exc:
        raise VoucherServiceError('Voucher no encontrado.') from exc


def list_user_vouchers(*, user):
    """Return travel vouchers for the authenticated user, newest first."""
    return TravelVoucher.objects.filter(user=user).select_related('quote').order_by('-created_at')
