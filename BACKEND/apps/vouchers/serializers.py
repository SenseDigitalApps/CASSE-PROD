"""Serializers for voucher API."""
from rest_framework import serializers

from apps.vouchers.models import TravelVoucher


class TravelVoucherSerializer(serializers.ModelSerializer):
    quote_id = serializers.UUIDField(source='quote.id', read_only=True)
    payment_id = serializers.UUIDField(source='payment.id', read_only=True, allow_null=True)
    has_pdf = serializers.SerializerMethodField()

    class Meta:
        model = TravelVoucher
        fields = (
            'id',
            'quote_id',
            'payment_id',
            'voucher_number_siebel',
            'control_number',
            'status',
            'error_code',
            'error_message',
            'has_pdf',
            'issued_at',
            'created_at',
        )
        read_only_fields = fields

    def get_has_pdf(self, obj: TravelVoucher) -> bool:
        return bool(obj.pdf_path)


class TravelVoucherListSerializer(serializers.ModelSerializer):
    quote_id = serializers.UUIDField(source='quote.id', read_only=True)
    destination_siebel = serializers.CharField(source='quote.destination_siebel', read_only=True)
    trip_type = serializers.CharField(source='quote.trip_type', read_only=True)
    start_date = serializers.DateField(source='quote.start_date', read_only=True)
    end_date = serializers.DateField(source='quote.end_date', read_only=True)
    has_pdf = serializers.SerializerMethodField()

    class Meta:
        model = TravelVoucher
        fields = (
            'id',
            'quote_id',
            'voucher_number_siebel',
            'status',
            'destination_siebel',
            'trip_type',
            'start_date',
            'end_date',
            'has_pdf',
            'issued_at',
            'created_at',
        )
        read_only_fields = fields

    def get_has_pdf(self, obj: TravelVoucher) -> bool:
        return bool(obj.pdf_path)


class IssueVoucherSerializer(serializers.Serializer):
    quote_id = serializers.UUIDField()
    payment_id = serializers.UUIDField()
