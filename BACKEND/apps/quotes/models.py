"""Travel assistance quote models."""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class TravelQuote(models.Model):
    """A travel assistance quote session (24h validity)."""

    class AffiliateType(models.TextChoices):
        INDIVIDUAL = 'INDIVIDUAL', 'No asociado'
        CAVIPETROL = 'CAVIPETROL', 'Asociado Cavipetrol'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Borrador'
        QUOTED = 'QUOTED', 'Cotizada'
        EXPIRED = 'EXPIRED', 'Expirada'
        SELECTED = 'SELECTED', 'Plan seleccionado'
        ASSIGNED = 'ASSIGNED', 'Asignada a comercial'
        CONVERTED = 'CONVERTED', 'Convertida'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='travel_quotes',
    )
    lead_id_siebel = models.CharField(max_length=32, blank=True, default='')
    quote_count = models.PositiveSmallIntegerField(default=0)
    affiliate_type = models.CharField(
        max_length=16,
        choices=AffiliateType.choices,
        default=AffiliateType.INDIVIDUAL,
    )
    origin_country = models.CharField(max_length=50, default='COLOMBIA')
    destination_ui_code = models.CharField(max_length=50, blank=True, default='')
    destination_siebel = models.CharField(max_length=100)
    trip_type = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    passenger_count = models.PositiveSmallIntegerField()
    passenger_ages = models.JSONField(default=list)
    category = models.CharField(max_length=50, blank=True, default='')
    contact_first_name = models.CharField(max_length=100, blank=True, default='')
    contact_last_name = models.CharField(max_length=100, blank=True, default='')
    contact_email = models.EmailField(blank=True, default='')
    contact_phone = models.CharField(max_length=40, blank=True, default='')
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    selected_product = models.ForeignKey(
        'QuoteProduct',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='selected_in_quotes',
    )
    app_reference = models.CharField(max_length=32, blank=True, default='', db_index=True)
    insurer_reference = models.CharField(max_length=64, blank=True, default='')
    insurer_name = models.CharField(max_length=100, blank=True, default='')
    assigned_commercial_name = models.CharField(max_length=255, blank=True, default='')
    assigned_commercial_email = models.EmailField(blank=True, default='')
    assigned_commercial_title = models.CharField(max_length=120, blank=True, default='')
    client_notified_at = models.DateTimeField(null=True, blank=True)
    commercial_notified_at = models.DateTimeField(null=True, blank=True)
    selected_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cotización de viaje'
        verbose_name_plural = 'Cotizaciones de viaje'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'expires_at']),
        ]

    def __str__(self):
        return f'Quote {self.id} [{self.status}]'

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def mark_expired_if_needed(self) -> bool:
        if self.is_expired and self.status not in (
            self.Status.EXPIRED,
            self.Status.CONVERTED,
        ):
            self.status = self.Status.EXPIRED
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False

    @property
    def display_insurer_name(self) -> str:
        if self.insurer_name:
            return self.insurer_name
        if self.selected_product and self.selected_product.brand:
            return self.selected_product.brand
        return 'Universal Assistance'

    @classmethod
    def default_expires_at(cls):
        hours = getattr(settings, 'QUOTE_EXPIRATION_HOURS', 24)
        return timezone.now() + timedelta(hours=hours)


class QuoteProduct(models.Model):
    """Product option returned by Universal Assistance for a quote."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote = models.ForeignKey(
        TravelQuote,
        on_delete=models.CASCADE,
        related_name='products',
    )
    product_id_siebel = models.CharField(max_length=32, db_index=True)
    product_name = models.CharField(max_length=200)
    family = models.CharField(max_length=100, blank=True, default='')
    category = models.CharField(max_length=100, blank=True, default='')
    brand = models.CharField(max_length=100, blank=True, default='')
    logo = models.CharField(max_length=100, blank=True, default='')
    price_emission = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_emission_local = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_gross = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_gross_local = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_unit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_net = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_net_local = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, blank=True, default='')
    currency_local = models.CharField(max_length=10, blank=True, default='')
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    geographic_scope = models.CharField(max_length=100, blank=True, default='')
    age_limit_lower = models.PositiveSmallIntegerField(null=True, blank=True)
    age_limit_upper = models.PositiveSmallIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=10, blank=True, default='')
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Producto cotizado'
        verbose_name_plural = 'Productos cotizados'
        ordering = ['price_emission_local', 'product_name']
        indexes = [
            models.Index(fields=['quote', 'product_id_siebel']),
        ]

    def __str__(self):
        return self.product_name


class QuoteProductAttribute(models.Model):
    """Coverage attribute for a quoted product."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        QuoteProduct,
        on_delete=models.CASCADE,
        related_name='attributes',
    )
    name = models.CharField(max_length=300)
    visible_name = models.CharField(max_length=300, blank=True, default='')
    unit = models.CharField(max_length=50, blank=True, default='')
    value = models.CharField(max_length=200, blank=True, default='')
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Atributo de cobertura'
        verbose_name_plural = 'Atributos de cobertura'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.visible_name or self.name


class QuotePassenger(models.Model):
    """Traveler identity data required for voucher issuance (DatosSolicitante)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote = models.ForeignKey(
        TravelQuote,
        on_delete=models.CASCADE,
        related_name='passengers',
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    document_type = models.CharField(max_length=30)
    document_number = models.CharField(max_length=40)
    birth_date = models.DateField()
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=40, blank=True, default='')
    residence_country = models.CharField(max_length=50, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pasajero de cotización'
        verbose_name_plural = 'Pasajeros de cotización'
        ordering = ['sort_order', 'last_name', 'first_name']
        constraints = [
            models.UniqueConstraint(
                fields=['quote', 'sort_order'],
                name='quotes_passenger_unique_sort_order',
            ),
        ]

    def __str__(self):
        return f'{self.first_name} {self.last_name}'


class AutoQuote(models.Model):
    """Allianz autos individual quote session (Call4, ramos 1241/1243)."""

    class AffiliateType(models.TextChoices):
        INDIVIDUAL = 'INDIVIDUAL', 'No asociado'
        CAVIPETROL = 'CAVIPETROL', 'Asociado Cavipetrol'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Borrador'
        QUOTED = 'QUOTED', 'Cotizada'
        EXPIRED = 'EXPIRED', 'Expirada'
        SELECTED = 'SELECTED', 'Plan seleccionado'
        ASSIGNED = 'ASSIGNED', 'Asignada a comercial'
        CONVERTED = 'CONVERTED', 'Convertida'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='auto_quotes',
    )
    affiliate_type = models.CharField(
        max_length=16,
        choices=AffiliateType.choices,
        default=AffiliateType.INDIVIDUAL,
    )
    product_code = models.CharField(max_length=8, default='1243')
    vehicle_plate = models.CharField(max_length=12)
    vehicle_year = models.PositiveSmallIntegerField(null=True, blank=True)
    fasecolda_code = models.CharField(max_length=20, blank=True, default='')
    risk_type = models.CharField(max_length=16, default='L0008')
    is_new_vehicle = models.BooleanField(default=False)
    in_dealership = models.BooleanField(default=False)
    insured_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    circulation_dane_code = models.CharField(max_length=10, blank=True, default='11001')
    circulation_city_name = models.CharField(max_length=120, blank=True, default='')
    holder_doc_type = models.CharField(max_length=4, default='C')
    holder_doc_number = models.CharField(max_length=32)
    holder_born_date = models.DateField()
    holder_sex = models.CharField(max_length=1, default='M')
    is_holder_driver = models.BooleanField(default=True)
    is_holder_owner = models.BooleanField(default=True)
    effective_date = models.DateField()
    term_date = models.DateField()
    allianz_quotation_number = models.CharField(max_length=64, blank=True, default='')
    vehicle_brand = models.CharField(max_length=80, blank=True, default='')
    vehicle_line = models.CharField(max_length=120, blank=True, default='')
    vehicle_version = models.CharField(max_length=200, blank=True, default='')
    contact_first_name = models.CharField(max_length=100, blank=True, default='')
    contact_last_name = models.CharField(max_length=100, blank=True, default='')
    contact_email = models.EmailField(blank=True, default='')
    contact_phone = models.CharField(max_length=40, blank=True, default='')
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    selected_product = models.ForeignKey(
        'AutoQuotePackage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='selected_in_quotes',
    )
    app_reference = models.CharField(max_length=32, blank=True, default='', db_index=True)
    insurer_reference = models.CharField(max_length=64, blank=True, default='')
    insurer_name = models.CharField(max_length=100, blank=True, default='')
    assigned_commercial_name = models.CharField(max_length=255, blank=True, default='')
    assigned_commercial_email = models.EmailField(blank=True, default='')
    assigned_commercial_title = models.CharField(max_length=120, blank=True, default='')
    client_notified_at = models.DateTimeField(null=True, blank=True)
    commercial_notified_at = models.DateTimeField(null=True, blank=True)
    selected_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cotización de autos'
        verbose_name_plural = 'Cotizaciones de autos'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'expires_at']),
            models.Index(fields=['vehicle_plate']),
        ]

    def __str__(self):
        return f'AutoQuote {self.vehicle_plate} [{self.status}]'

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def mark_expired_if_needed(self) -> bool:
        if self.is_expired and self.status not in (
            self.Status.EXPIRED,
            self.Status.CONVERTED,
        ):
            self.status = self.Status.EXPIRED
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False

    @property
    def display_insurer_name(self) -> str:
        if self.insurer_name:
            return self.insurer_name
        if self.selected_product and self.selected_product.brand:
            return self.selected_product.brand
        return 'Allianz'

    # Duck-typing helpers for shared commercial email templates.
    @property
    def destination_siebel(self) -> str:
        brand = self.vehicle_brand or ''
        line = self.vehicle_line or ''
        return f'{self.vehicle_plate} · {brand} {line}'.strip(' ·')

    @property
    def start_date(self):
        return self.effective_date

    @property
    def end_date(self):
        return self.term_date

    @classmethod
    def default_expires_at(cls):
        hours = getattr(settings, 'QUOTE_EXPIRATION_HOURS', 24)
        return timezone.now() + timedelta(hours=hours)


class AutoQuotePackage(models.Model):
    """Allianz package option for an auto quote (maps to comparativo UI cards)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote = models.ForeignKey(
        AutoQuote,
        on_delete=models.CASCADE,
        related_name='products',
    )
    package_id = models.CharField(max_length=32, db_index=True)
    # Aliases used by travel-compatible serializers / commercial emails.
    product_id_siebel = models.CharField(max_length=32, db_index=True)
    product_name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, blank=True, default='Allianz')
    logo = models.CharField(max_length=100, blank=True, default='allianz')
    price_emission = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_emission_local = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_gross = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_gross_local = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_unit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_net = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    price_net_local = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    premium_annual = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    premium_monthly = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    premium_semestral = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    premium_trimestral = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, blank=True, default='COP')
    currency_local = models.CharField(max_length=10, blank=True, default='COP')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Paquete autos cotizado'
        verbose_name_plural = 'Paquetes autos cotizados'
        ordering = ['price_emission_local', 'product_name']
        indexes = [
            models.Index(fields=['quote', 'package_id']),
        ]

    def __str__(self):
        return self.product_name


class AutoQuoteCoverage(models.Model):
    """Coverage row inside an Allianz package."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        AutoQuotePackage,
        on_delete=models.CASCADE,
        related_name='attributes',
    )
    coverage_id = models.CharField(max_length=32, blank=True, default='')
    name = models.CharField(max_length=300)
    visible_name = models.CharField(max_length=300, blank=True, default='')
    unit = models.CharField(max_length=50, blank=True, default='')
    value = models.CharField(max_length=200, blank=True, default='')
    deductible = models.CharField(max_length=64, blank=True, default='')
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Cobertura autos'
        verbose_name_plural = 'Coberturas autos'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.visible_name or self.name
