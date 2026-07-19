"""Serializers for travel quote API."""
from rest_framework import serializers

from apps.quotes.models import QuotePassenger, QuoteProduct, QuoteProductAttribute, TravelQuote


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
