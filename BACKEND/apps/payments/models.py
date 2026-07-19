"""Payment models for travel quote checkout."""
import uuid

from django.conf import settings
from django.db import models


class Payment(models.Model):
    """Payment attempt linked to a travel quote."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        COMPLETED = 'COMPLETED', 'Completado'
        FAILED = 'FAILED', 'Fallido'
        REFUNDED = 'REFUNDED', 'Reembolsado'

    class Provider(models.TextChoices):
        MOCK = 'MOCK', 'Simulado'
        WOMPI = 'WOMPI', 'Wompi'
        PSE = 'PSE', 'PSE'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments',
    )
    quote = models.ForeignKey(
        'quotes.TravelQuote',
        on_delete=models.CASCADE,
        related_name='payments',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    method = models.CharField(max_length=30, blank=True, default='')
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    provider = models.CharField(
        max_length=16,
        choices=Provider.choices,
        default=Provider.MOCK,
    )
    provider_reference = models.CharField(max_length=100, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['quote', 'status']),
        ]

    def __str__(self):
        return f'Payment {self.id} [{self.status}]'
