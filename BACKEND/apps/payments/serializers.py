"""Serializers for payments API."""
from rest_framework import serializers

from apps.payments.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    quote_id = serializers.UUIDField(source='quote.id', read_only=True)

    class Meta:
        model = Payment
        fields = (
            'id',
            'quote_id',
            'amount',
            'currency',
            'method',
            'status',
            'provider',
            'provider_reference',
            'completed_at',
            'created_at',
        )
        read_only_fields = fields


class InitiatePaymentSerializer(serializers.Serializer):
    method = serializers.CharField(required=False, allow_blank=True, default='MOCK')
