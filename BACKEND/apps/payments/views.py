"""Payment API views."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.payments.models import Payment
from apps.payments.serializers import InitiatePaymentSerializer, PaymentSerializer
from apps.payments.services.payment_service import (
    PaymentServiceError,
    confirm_mock_payment,
    initiate_travel_payment,
)
from apps.quotes.services.quote_service import QuoteServiceError, get_user_quote


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


class TravelQuotePaymentInitiateView(APIView):
    """POST /api/v1/payments/travel-quotes/<uuid>/initiate/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, quote_id):
        serializer = InitiatePaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            quote = get_user_quote(user=request.user, quote_id=quote_id)
            payment = initiate_travel_payment(
                user=request.user,
                quote=quote,
                method=serializer.validated_data.get('method', ''),
                ip_address=get_client_ip(request),
            )
        except (QuoteServiceError, PaymentServiceError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentDetailView(APIView):
    """GET /api/v1/payments/<uuid>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, payment_id):
        try:
            payment = Payment.objects.get(id=payment_id, user=request.user)
        except Payment.DoesNotExist:
            return Response({'detail': 'Pago no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(PaymentSerializer(payment).data)


class PaymentConfirmView(APIView):
    """POST /api/v1/payments/<uuid>/confirm/ — mock confirmation for QA."""
    permission_classes = [IsAuthenticated]

    def post(self, request, payment_id):
        try:
            payment = Payment.objects.select_related('quote').get(
                id=payment_id,
                user=request.user,
            )
            payment = confirm_mock_payment(
                payment=payment,
                ip_address=get_client_ip(request),
            )
        except Payment.DoesNotExist:
            return Response({'detail': 'Pago no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        except PaymentServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PaymentSerializer(payment).data)
