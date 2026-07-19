"""Payment business logic (mock provider for Phase 4)."""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.constants import PAYMENT_COMPLETED, PAYMENT_CREATED, PAYMENT_FAILED
from apps.audit.services.audit_log import log_audit_event
from apps.payments.models import Payment
from apps.quotes.models import TravelQuote


class PaymentServiceError(Exception):
    """Raised when payment operations fail."""


def _get_quote_amount(quote: TravelQuote) -> tuple[Decimal, str]:
    if not quote.selected_product:
        raise PaymentServiceError('La cotización no tiene producto seleccionado.')
    product = quote.selected_product
    amount = product.price_emission or product.price_emission_local
    if amount is None:
        raise PaymentServiceError('El producto seleccionado no tiene precio.')
    currency = product.currency or product.currency_local or 'USD'
    return amount, currency


@transaction.atomic
def initiate_travel_payment(
    *,
    user,
    quote: TravelQuote,
    method: str = '',
    ip_address: str | None = None,
) -> Payment:
    from django.conf import settings

    if not getattr(settings, 'ENABLE_IN_APP_TRAVEL_PAYMENTS', False):
        raise PaymentServiceError(
            'El pago no se realiza en la aplicación. '
            'Un ejecutivo de CASSE Seguros te contactará para gestionar el cobro.'
        )

    quote.mark_expired_if_needed()
    if quote.is_expired:
        raise PaymentServiceError('La cotización expiró.')
    if quote.status not in (TravelQuote.Status.SELECTED, TravelQuote.Status.ASSIGNED):
        raise PaymentServiceError('La cotización debe tener un plan seleccionado.')
    if not quote.passengers.exists():
        raise PaymentServiceError(
            'Debe registrar los datos de los pasajeros antes del pago.'
        )

    existing = quote.payments.filter(status=Payment.Status.PENDING).first()
    if existing:
        return existing

    amount, currency = _get_quote_amount(quote)
    payment = Payment.objects.create(
        user=user,
        quote=quote,
        amount=amount,
        currency=currency,
        method=method or 'MOCK',
        status=Payment.Status.PENDING,
        provider=Payment.Provider.MOCK,
    )

    log_audit_event(
        actor_user=user,
        action=PAYMENT_CREATED,
        entity='Payment',
        entity_id=payment.id,
        metadata={'quote_id': str(quote.id), 'amount': str(amount), 'currency': currency},
        ip_address=ip_address,
    )
    return payment


@transaction.atomic
def confirm_mock_payment(
    *,
    payment: Payment,
    ip_address: str | None = None,
) -> Payment:
    if payment.status == Payment.Status.COMPLETED:
        return payment
    if payment.status != Payment.Status.PENDING:
        raise PaymentServiceError('El pago no está pendiente de confirmación.')

    payment.status = Payment.Status.COMPLETED
    payment.provider_reference = f'MOCK-{payment.id}'
    payment.completed_at = timezone.now()
    payment.save(update_fields=[
        'status', 'provider_reference', 'completed_at', 'updated_at',
    ])

    log_audit_event(
        actor_user=payment.user,
        action=PAYMENT_COMPLETED,
        entity='Payment',
        entity_id=payment.id,
        metadata={'quote_id': str(payment.quote_id)},
        ip_address=ip_address,
    )
    return payment


@transaction.atomic
def fail_payment(*, payment: Payment, reason: str = '', ip_address: str | None = None) -> Payment:
    payment.status = Payment.Status.FAILED
    payment.metadata = {**payment.metadata, 'failure_reason': reason}
    payment.save(update_fields=['status', 'metadata', 'updated_at'])

    log_audit_event(
        actor_user=payment.user,
        action=PAYMENT_FAILED,
        entity='Payment',
        entity_id=payment.id,
        metadata={'reason': reason},
        ip_address=ip_address,
    )
    return payment
