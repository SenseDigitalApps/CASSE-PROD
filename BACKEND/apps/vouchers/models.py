"""Travel assistance voucher persistence."""
import uuid

from django.conf import settings
from django.db import models


class TravelVoucher(models.Model):
    """Voucher issued in Siebel for a converted travel quote."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        ISSUING = 'ISSUING', 'Emitiendo'
        ISSUED = 'ISSUED', 'Emitido'
        ERROR = 'ERROR', 'Error'
        CANCELLED = 'CANCELLED', 'Anulado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='travel_vouchers',
    )
    quote = models.OneToOneField(
        'quotes.TravelQuote',
        on_delete=models.CASCADE,
        related_name='voucher',
    )
    payment = models.ForeignKey(
        'payments.Payment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vouchers',
    )
    voucher_number_siebel = models.CharField(max_length=32, blank=True, default='')
    control_number = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    error_code = models.CharField(max_length=20, blank=True, default='')
    error_message = models.TextField(blank=True, default='')
    pdf_path = models.CharField(max_length=500, blank=True, default='')
    raw_alta_response = models.JSONField(default=dict, blank=True)
    raw_portal_response = models.JSONField(default=dict, blank=True)
    raw_report_response = models.JSONField(default=dict, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Voucher de viaje'
        verbose_name_plural = 'Vouchers de viaje'
        ordering = ['-created_at']

    def __str__(self):
        return self.voucher_number_siebel or str(self.id)
