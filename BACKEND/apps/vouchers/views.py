"""Voucher API views."""
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.constants import VOUCHER_PDF_FETCHED
from apps.audit.services.audit_log import log_audit_event
from apps.payments.models import Payment
from apps.quotes.services.quote_service import QuoteServiceError, get_user_quote
from apps.vouchers.serializers import (
    IssueVoucherSerializer,
    TravelVoucherListSerializer,
    TravelVoucherSerializer,
)
from apps.vouchers.services.voucher_service import (
    VoucherServiceError,
    get_user_voucher,
    issue_travel_voucher,
    list_user_vouchers,
)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


class PdfFileRenderer(BaseRenderer):
    """Allow DRF content negotiation for binary PDF responses."""

    media_type = 'application/pdf'
    format = 'pdf'
    charset = None
    render_style = 'binary'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class VoucherListView(APIView):
    """GET /api/v1/vouchers/ — certificados emitidos del usuario."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        vouchers = list_user_vouchers(user=request.user)
        serializer = TravelVoucherListSerializer(vouchers, many=True)
        return Response({'items': serializer.data})


class VoucherIssueView(APIView):
    """POST /api/v1/vouchers/issue/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.conf import settings

        if not getattr(settings, 'ENABLE_IN_APP_TRAVEL_VOUCHER_ISSUE', False):
            return Response(
                {
                    'detail': (
                        'La emisión de pólizas no está disponible en la aplicación. '
                        'Un ejecutivo de CASSE Seguros realizará la emisión tras confirmar el pago.'
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = IssueVoucherSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        quote_id = serializer.validated_data['quote_id']
        payment_id = serializer.validated_data['payment_id']

        try:
            quote = get_user_quote(user=request.user, quote_id=quote_id)
            payment = Payment.objects.get(id=payment_id, user=request.user)
            voucher = issue_travel_voucher(
                user=request.user,
                quote=quote,
                payment=payment,
                ip_address=get_client_ip(request),
                correlation_id=request.META.get('CORRELATION_ID', ''),
            )
        except QuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except Payment.DoesNotExist:
            return Response({'detail': 'Pago no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        except VoucherServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TravelVoucherSerializer(voucher).data, status=status.HTTP_201_CREATED)


class VoucherDetailView(APIView):
    """GET /api/v1/vouchers/<uuid>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, voucher_id):
        try:
            voucher = get_user_voucher(user=request.user, voucher_id=voucher_id)
        except VoucherServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(TravelVoucherSerializer(voucher).data)


class VoucherPdfView(APIView):
    """GET /api/v1/vouchers/<uuid>/pdf/"""
    permission_classes = [IsAuthenticated]
    renderer_classes = [PdfFileRenderer]

    def get(self, request, voucher_id):
        try:
            voucher = get_user_voucher(user=request.user, voucher_id=voucher_id)
        except VoucherServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)

        if not voucher.pdf_path:
            return Response(
                {'detail': 'PDF no disponible para este voucher.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        pdf_file = Path(settings.MEDIA_ROOT) / voucher.pdf_path
        if not pdf_file.exists():
            raise Http404('Archivo PDF no encontrado.')

        log_audit_event(
            actor_user=request.user,
            action=VOUCHER_PDF_FETCHED,
            entity='TravelVoucher',
            entity_id=voucher.id,
            metadata={'voucher_number': voucher.voucher_number_siebel},
            ip_address=get_client_ip(request),
        )
        return FileResponse(
            pdf_file.open('rb'),
            content_type='application/pdf',
            as_attachment=True,
            filename=f'voucher-{voucher.voucher_number_siebel or voucher.id}.pdf',
        )
