"""Serializers for travel quote API."""
from rest_framework import serializers

from apps.quotes.models import (
    AutoQuote,
    AutoQuoteCoverage,
    AutoQuotePackage,
    QuotePassenger,
    QuoteProduct,
    QuoteProductAttribute,
    TravelQuote,
)


class QuotePassengerSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotePassenger
        fields = (
            'id',
            'sort_order',
            'first_name',
            'last_name',
            'document_type',
            'document_number',
            'birth_date',
            'email',
            'phone',
            'residence_country',
            'city',
        )
        read_only_fields = ('id',)


class QuotePassengerWriteSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    document_type = serializers.CharField(max_length=30)
    document_number = serializers.CharField(max_length=40)
    birth_date = serializers.DateField()
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=40)
    residence_country = serializers.CharField(required=False, allow_blank=True, max_length=50)
    city = serializers.CharField(required=False, allow_blank=True, max_length=100)


class SaveQuotePassengersSerializer(serializers.Serializer):
    passengers = QuotePassengerWriteSerializer(many=True, min_length=1, max_length=10)


class QuoteProductAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuoteProductAttribute
        fields = ('name', 'visible_name', 'unit', 'value')


class QuoteProductSerializer(serializers.ModelSerializer):
    coverage_attributes = QuoteProductAttributeSerializer(source='attributes', many=True)
    prices = serializers.SerializerMethodField()

    class Meta:
        model = QuoteProduct
        fields = (
            'id',
            'product_id_siebel',
            'product_name',
            'family',
            'category',
            'brand',
            'logo',
            'prices',
            'geographic_scope',
            'age_limit_lower',
            'age_limit_upper',
            'coverage_attributes',
        )

    def get_prices(self, obj: QuoteProduct) -> dict:
        return {
            'emission': obj.price_emission,
            'emission_local': obj.price_emission_local,
            'gross': obj.price_gross,
            'gross_local': obj.price_gross_local,
            'unit': obj.price_unit,
            'net': obj.price_net,
            'net_local': obj.price_net_local,
            'currency': obj.currency,
            'currency_local': obj.currency_local,
            'exchange_rate': obj.exchange_rate,
        }


class TravelQuoteListSerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)
    selected_product_id = serializers.UUIDField(
        source='selected_product.id',
        read_only=True,
        allow_null=True,
    )
    insurer_display = serializers.CharField(source='display_insurer_name', read_only=True)

    class Meta:
        model = TravelQuote
        fields = (
            'id',
            'status',
            'affiliate_type',
            'affiliation_number',
            'destination_ui_code',
            'destination_siebel',
            'trip_type',
            'start_date',
            'end_date',
            'passenger_count',
            'lead_id_siebel',
            'quote_count',
            'products_count',
            'selected_product_id',
            'app_reference',
            'insurer_reference',
            'insurer_display',
            'assigned_commercial_name',
            'is_expired',
            'expires_at',
            'created_at',
        )

    def get_products_count(self, obj: TravelQuote) -> int:
        if hasattr(obj, '_prefetched_objects_cache') and 'products' in obj._prefetched_objects_cache:
            return len(obj.products.all())
        return obj.products.count()


class TravelQuoteDetailSerializer(serializers.ModelSerializer):
    products = QuoteProductSerializer(many=True, read_only=True)
    passengers = QuotePassengerSerializer(many=True, read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    selected_product = QuoteProductSerializer(read_only=True)
    insurer_display = serializers.CharField(source='display_insurer_name', read_only=True)
    client_notification_label = serializers.SerializerMethodField()

    class Meta:
        model = TravelQuote
        fields = (
            'id',
            'status',
            'affiliate_type',
            'affiliation_number',
            'payment_form',
            'paying_company',
            'origin_country',
            'destination_ui_code',
            'destination_siebel',
            'trip_type',
            'start_date',
            'end_date',
            'passenger_count',
            'passenger_ages',
            'category',
            'contact_first_name',
            'contact_last_name',
            'contact_email',
            'contact_phone',
            'lead_id_siebel',
            'quote_count',
            'products',
            'passengers',
            'selected_product',
            'app_reference',
            'insurer_reference',
            'insurer_name',
            'insurer_display',
            'assigned_commercial_name',
            'assigned_commercial_email',
            'assigned_commercial_title',
            'client_notified_at',
            'commercial_notified_at',
            'client_notification_label',
            'selected_at',
            'is_expired',
            'expires_at',
            'created_at',
            'updated_at',
        )

    def get_client_notification_label(self, obj: TravelQuote) -> str:
        from apps.quotes.services.commercial_assignment import relative_notified_label
        return relative_notified_label(obj.client_notified_at)


class TravelQuoteCreateSerializer(serializers.Serializer):
    affiliate_type = serializers.ChoiceField(
        choices=TravelQuote.AffiliateType.choices,
        default=TravelQuote.AffiliateType.INDIVIDUAL,
    )
    affiliation_number = serializers.CharField(required=False, allow_blank=True, default='')
    payment_form = serializers.CharField(required=False, allow_blank=True, default='')
    paying_company = serializers.CharField(required=False, allow_blank=True, default='')
    destination_ui_code = serializers.CharField(required=False, allow_blank=True)
    destination_siebel = serializers.CharField(required=False, allow_blank=True)
    origin_country = serializers.CharField(required=False, allow_blank=True)
    trip_type = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    passenger_count = serializers.IntegerField(min_value=1, max_value=10)
    passenger_ages = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=120),
        min_length=1,
        max_length=10,
    )
    category = serializers.CharField(required=False, allow_blank=True, default='')
    contact_first_name = serializers.CharField(required=False, allow_blank=True)
    contact_last_name = serializers.CharField(required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get('destination_ui_code') and not attrs.get('destination_siebel'):
            raise serializers.ValidationError(
                'Se requiere destination_ui_code o destination_siebel.'
            )
        if attrs['end_date'] < attrs['start_date']:
            raise serializers.ValidationError('end_date debe ser posterior a start_date.')
        if len(attrs['passenger_ages']) < attrs['passenger_count']:
            raise serializers.ValidationError(
                'passenger_ages debe incluir al menos passenger_count edades.'
            )
        return attrs


class TravelQuoteRequoteSerializer(serializers.Serializer):
    affiliate_type = serializers.ChoiceField(
        choices=TravelQuote.AffiliateType.choices,
        required=False,
    )
    destination_ui_code = serializers.CharField(required=False, allow_blank=True)
    destination_siebel = serializers.CharField(required=False, allow_blank=True)
    origin_country = serializers.CharField(required=False, allow_blank=True)
    trip_type = serializers.CharField(required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    passenger_count = serializers.IntegerField(min_value=1, max_value=10, required=False)
    passenger_ages = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=120),
        required=False,
        min_length=1,
        max_length=10,
    )
    category = serializers.CharField(required=False, allow_blank=True)
    contact_first_name = serializers.CharField(required=False, allow_blank=True)
    contact_last_name = serializers.CharField(required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(required=False, allow_blank=True)


class SelectProductSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()


class AutoQuoteCoverageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoQuoteCoverage
        fields = ('coverage_id', 'name', 'visible_name', 'unit', 'value', 'deductible')


class AutoQuotePackageSerializer(serializers.ModelSerializer):
    coverage_attributes = AutoQuoteCoverageSerializer(source='attributes', many=True)
    prices = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()

    class Meta:
        model = AutoQuotePackage
        fields = (
            'id',
            'package_id',
            'product_id_siebel',
            'product_name',
            'brand',
            'logo',
            'prices',
            'payments',
            'coverage_attributes',
        )

    def get_prices(self, obj: AutoQuotePackage) -> dict:
        return {
            'emission': obj.price_emission,
            'emission_local': obj.price_emission_local,
            'gross': obj.price_gross,
            'gross_local': obj.price_gross_local,
            'unit': obj.price_unit,
            'net': obj.price_net,
            'net_local': obj.price_net_local,
            'currency': obj.currency,
            'currency_local': obj.currency_local,
        }

    def get_payments(self, obj: AutoQuotePackage) -> dict:
        return {
            'annual': obj.premium_annual,
            'monthly': obj.premium_monthly,
            'semestral': obj.premium_semestral,
            'trimestral': obj.premium_trimestral,
        }


class AutoQuoteListSerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)
    selected_product_id = serializers.UUIDField(
        source='selected_product.id',
        read_only=True,
        allow_null=True,
    )
    insurer_display = serializers.CharField(source='display_insurer_name', read_only=True)

    class Meta:
        model = AutoQuote
        fields = (
            'id',
            'status',
            'affiliate_type',
            'affiliation_number',
            'payment_form',
            'paying_company',
            'vehicle_plate',
            'vehicle_brand',
            'vehicle_line',
            'vehicle_year',
            'allianz_quotation_number',
            'products_count',
            'selected_product_id',
            'app_reference',
            'insurer_reference',
            'insurer_display',
            'assigned_commercial_name',
            'is_expired',
            'expires_at',
            'created_at',
        )

    def get_products_count(self, obj: AutoQuote) -> int:
        if hasattr(obj, '_prefetched_objects_cache') and 'products' in obj._prefetched_objects_cache:
            return len(obj.products.all())
        return obj.products.count()


class AutoQuoteDetailSerializer(serializers.ModelSerializer):
    products = AutoQuotePackageSerializer(many=True, read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    selected_product = AutoQuotePackageSerializer(read_only=True)
    insurer_display = serializers.CharField(source='display_insurer_name', read_only=True)
    client_notification_label = serializers.SerializerMethodField()

    class Meta:
        model = AutoQuote
        fields = (
            'id',
            'status',
            'affiliate_type',
            'affiliation_number',
            'payment_form',
            'paying_company',
            'product_code',
            'vehicle_plate',
            'vehicle_year',
            'fasecolda_code',
            'risk_type',
            'is_new_vehicle',
            'in_dealership',
            'insured_value',
            'circulation_dane_code',
            'circulation_city_name',
            'holder_doc_type',
            'holder_doc_number',
            'holder_born_date',
            'holder_sex',
            'is_holder_driver',
            'is_holder_owner',
            'effective_date',
            'term_date',
            'allianz_quotation_number',
            'vehicle_brand',
            'vehicle_line',
            'vehicle_version',
            'contact_first_name',
            'contact_last_name',
            'contact_email',
            'contact_phone',
            'products',
            'selected_product',
            'app_reference',
            'insurer_reference',
            'insurer_name',
            'insurer_display',
            'assigned_commercial_name',
            'assigned_commercial_email',
            'assigned_commercial_title',
            'client_notified_at',
            'commercial_notified_at',
            'client_notification_label',
            'selected_at',
            'is_expired',
            'expires_at',
            'created_at',
            'updated_at',
        )

    def get_client_notification_label(self, obj: AutoQuote) -> str:
        from apps.quotes.services.commercial_assignment import relative_notified_label
        return relative_notified_label(obj.client_notified_at)


class AutoQuoteCreateSerializer(serializers.Serializer):
    affiliate_type = serializers.ChoiceField(
        choices=AutoQuote.AffiliateType.choices,
        default=AutoQuote.AffiliateType.INDIVIDUAL,
    )
    affiliation_number = serializers.CharField(required=False, allow_blank=True, default='')
    payment_form = serializers.CharField(required=False, allow_blank=True, default='')
    paying_company = serializers.CharField(required=False, allow_blank=True, default='')
    product_code = serializers.CharField(required=False, allow_blank=True, default='1243')
    vehicle_plate = serializers.CharField(max_length=12)
    vehicle_year = serializers.IntegerField(required=False, min_value=1980, max_value=2100)
    fasecolda_code = serializers.CharField(required=False, allow_blank=True, default='')
    risk_type = serializers.CharField(required=False, allow_blank=True, default='L0008')
    is_new_vehicle = serializers.BooleanField(required=False, default=False)
    in_dealership = serializers.BooleanField(required=False, default=False)
    insured_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, default=0,
    )
    circulation_dane_code = serializers.CharField(required=False, allow_blank=True, default='11001')
    circulation_city_name = serializers.CharField(required=False, allow_blank=True, default='')
    holder_doc_type = serializers.CharField(required=False, allow_blank=True, default='C')
    holder_doc_number = serializers.CharField(max_length=32)
    holder_born_date = serializers.DateField()
    holder_sex = serializers.CharField(required=False, allow_blank=True, default='M')
    is_holder_driver = serializers.BooleanField(required=False, default=True)
    is_holder_owner = serializers.BooleanField(required=False, default=True)
    effective_date = serializers.DateField(required=False)
    term_date = serializers.DateField(required=False)
    contact_first_name = serializers.CharField(required=False, allow_blank=True)
    contact_last_name = serializers.CharField(required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(required=False, allow_blank=True)
