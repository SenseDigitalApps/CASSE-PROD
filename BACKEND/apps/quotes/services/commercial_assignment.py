"""Assign commercial executive and notify after quote selection."""
from __future__ import annotations

import logging
from datetime import datetime

from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from apps.audit.constants import QUOTE_ASSIGNED_TO_COMMERCIAL
from apps.audit.services.audit_log import log_audit_event
from apps.common.services.email import send_quote_selected_emails
from apps.quotes.models import TravelQuote

logger = logging.getLogger(__name__)


def _next_app_reference() -> str:
    year = timezone.now().year
    prefix = f'CAS-{year}-'
    last = (
        TravelQuote.objects.filter(app_reference__startswith=prefix)
        .aggregate(Max('app_reference'))
        .get('app_reference__max')
    )
    seq = 1
    if last:
        try:
            seq = int(last.rsplit('-', 1)[-1]) + 1
        except (TypeError, ValueError):
            seq = TravelQuote.objects.filter(app_reference__startswith=prefix).count() + 1
    return f'{prefix}{seq:05d}'


def assign_commercial_for_quote(
    *,
    quote: TravelQuote,
    ip_address: str | None = None,
) -> TravelQuote:
    """
    Persist commercial assignment metadata and notify client + commercial.

    City/turn routing is not implemented yet; uses COMMERCIAL_DEFAULT_* settings.
    """
    product = quote.selected_product
    if not quote.app_reference:
        quote.app_reference = _next_app_reference()

    quote.insurer_reference = (
        (product.product_id_siebel if product else '')
        or quote.lead_id_siebel
        or ''
    )
    quote.insurer_name = (
        (product.brand if product and product.brand else '')
        or 'Universal Assistance'
    )
    quote.assigned_commercial_name = settings.COMMERCIAL_DEFAULT_NAME
    quote.assigned_commercial_email = settings.COMMERCIAL_DEFAULT_EMAIL
    quote.assigned_commercial_title = settings.COMMERCIAL_DEFAULT_TITLE
    quote.selected_at = quote.selected_at or timezone.now()
    quote.status = TravelQuote.Status.ASSIGNED

    client_ok, commercial_ok = send_quote_selected_emails(quote)
    now = timezone.now()
    if client_ok:
        quote.client_notified_at = now
    if commercial_ok:
        quote.commercial_notified_at = now

    quote.save(update_fields=[
        'app_reference',
        'insurer_reference',
        'insurer_name',
        'assigned_commercial_name',
        'assigned_commercial_email',
        'assigned_commercial_title',
        'selected_at',
        'client_notified_at',
        'commercial_notified_at',
        'status',
        'updated_at',
    ])

    log_audit_event(
        actor_user=quote.user,
        action=QUOTE_ASSIGNED_TO_COMMERCIAL,
        entity='TravelQuote',
        entity_id=quote.id,
        metadata={
            'app_reference': quote.app_reference,
            'commercial_email': quote.assigned_commercial_email,
            'client_notified': client_ok,
            'commercial_notified': commercial_ok,
        },
        ip_address=ip_address,
    )
    return quote


def relative_notified_label(notified_at: datetime | None) -> str:
    if not notified_at:
        return 'Pendiente de envío'
    delta = timezone.now() - notified_at
    if delta.total_seconds() < 120:
        return 'Enviado hace un momento'
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f'Enviado hace {minutes} min'
    hours = minutes // 60
    return f'Enviado hace {hours} h'
