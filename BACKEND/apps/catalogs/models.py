"""Catalog models for Universal Assistance list-of-values."""
from django.db import models


class CatalogEntry(models.Model):
    """Siebel LOV entry used to populate app dropdowns."""

    class CatalogType(models.TextChoices):
        DESTINATION = 'DESTINATION', 'Destino'
        TRIP_TYPE = 'TRIP_TYPE', 'Tipo de viaje'
        COUNTRY = 'COUNTRY', 'País'
        DOCUMENT_TYPE = 'DOCUMENT_TYPE', 'Tipo de documento'
        CHANNEL = 'CHANNEL', 'Canal'
        SALE_TYPE = 'SALE_TYPE', 'Tipo de venta'
        GENDER = 'GENDER', 'Sexo'
        VOUCHER_STATUS = 'VOUCHER_STATUS', 'Estado voucher'
        PAYMENT_METHOD = 'PAYMENT_METHOD', 'Medio de pago'
        COURTESY_TITLE = 'COURTESY_TITLE', 'Título cortesía'
        REASON_CODE = 'REASON_CODE', 'Código de razón'
        BILLING = 'BILLING', 'Facturación'
        LINE = 'LINE', 'Línea'
        VOUCHER_REASON = 'VOUCHER_REASON', 'Motivo voucher'
        ISSUER = 'ISSUER', 'Emisor'
        CURRENCY = 'CURRENCY', 'Moneda'

    catalog_type = models.CharField(max_length=32, choices=CatalogType.choices, db_index=True)
    code = models.CharField(max_length=100)
    label = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Entrada de catálogo'
        verbose_name_plural = 'Entradas de catálogo'
        ordering = ['catalog_type', 'sort_order', 'label']
        constraints = [
            models.UniqueConstraint(
                fields=['catalog_type', 'code'],
                name='uniq_catalog_type_code',
            ),
        ]
        indexes = [
            models.Index(fields=['catalog_type', 'is_active']),
        ]

    def __str__(self):
        return f'{self.catalog_type}: {self.label}'


class DestinationMapping(models.Model):
    """Maps CASSE app UI destination codes to Siebel values."""

    ui_code = models.CharField(max_length=50, unique=True)
    ui_label = models.CharField(max_length=100)
    siebel_value = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Mapeo de destino'
        verbose_name_plural = 'Mapeos de destino'
        ordering = ['sort_order', 'ui_label']

    def __str__(self):
        return f'{self.ui_code} → {self.siebel_value}'
