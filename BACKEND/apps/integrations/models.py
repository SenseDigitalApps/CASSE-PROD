"""
Models for external integration call logging.
"""
import uuid
from django.conf import settings
from django.db import models


class IntegrationCallLog(models.Model):
    """Audit log for outbound SOAP/API calls to Universal Assistance."""

    class Status(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Éxito'
        ERROR = 'ERROR', 'Error'
        TIMEOUT = 'TIMEOUT', 'Timeout'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_name = models.CharField(max_length=64, db_index=True)
    operation = models.CharField(max_length=128, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, db_index=True)
    request_payload = models.JSONField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='integration_calls',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Log de integración'
        verbose_name_plural = 'Logs de integración'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['service_name', 'operation']),
            models.Index(fields=['created_at', 'status']),
        ]

    def __str__(self):
        return f'{self.service_name}.{self.operation} [{self.status}]'
