"""Views for travel and auto quote endpoints."""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.quotes.serializers import (
    AutoQuoteCreateSerializer,
    AutoQuoteDetailSerializer,
    AutoQuoteListSerializer,
    HomeQuoteCreateSerializer,
    HomeQuoteDetailSerializer,
    HomeQuoteListSerializer,
    SaveQuotePassengersSerializer,
    SelectProductSerializer,
    TravelQuoteCreateSerializer,
    TravelQuoteDetailSerializer,
    TravelQuoteListSerializer,
    TravelQuoteRequoteSerializer,
)
from apps.quotes.services.auto_quote_service import (
    AutoQuoteServiceError,
    create_auto_quote,
    get_user_auto_quote,
    list_user_auto_quotes,
    select_auto_quote_product,
)
from apps.quotes.services.home_quote_service import (
    HomeQuoteServiceError,
    create_home_quote,
    get_user_home_quote,
    list_user_home_quotes,
    select_home_quote_product,
)
from apps.quotes.services.quote_service import (
    QuoteServiceError,
    create_travel_quote,
    get_user_quote,
    list_user_quotes,
    requote_travel_quote,
    save_quote_passengers,
    select_quote_product,
)

logger = logging.getLogger(__name__)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


class TravelQuoteListCreateView(APIView):
    """
    GET  /api/v1/quotes/travel/ — historial de cotizaciones activas
    POST /api/v1/quotes/travel/ — nueva cotización
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        include_expired = request.query_params.get('include_expired', '').lower() == 'true'
        quotes = list_user_quotes(user=request.user, include_expired=include_expired)
        serializer = TravelQuoteListSerializer(quotes, many=True)
        return Response({'items': serializer.data})

    def post(self, request):
        serializer = TravelQuoteCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            quote = create_travel_quote(
                user=request.user,
                data=serializer.validated_data,
                ip_address=get_client_ip(request),
                correlation_id=request.META.get('CORRELATION_ID', ''),
            )
        except QuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            TravelQuoteDetailSerializer(quote).data,
            status=status.HTTP_201_CREATED,
        )


class TravelQuoteDetailView(APIView):
    """GET /api/v1/quotes/travel/<uuid>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, quote_id):
        try:
            quote = get_user_quote(user=request.user, quote_id=quote_id)
        except QuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response(TravelQuoteDetailSerializer(quote).data)


class TravelQuoteRequoteView(APIView):
    """POST /api/v1/quotes/travel/<uuid>/requote/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, quote_id):
        serializer = TravelQuoteRequoteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            quote = get_user_quote(user=request.user, quote_id=quote_id)
            quote = requote_travel_quote(
                quote=quote,
                data=serializer.validated_data,
                ip_address=get_client_ip(request),
                correlation_id=request.META.get('CORRELATION_ID', ''),
            )
        except QuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TravelQuoteDetailSerializer(quote).data)


class TravelQuoteSelectProductView(APIView):
    """POST /api/v1/quotes/travel/<uuid>/select-product/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, quote_id):
        serializer = SelectProductSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            quote = get_user_quote(user=request.user, quote_id=quote_id)
            quote = select_quote_product(
                quote=quote,
                product_id=serializer.validated_data['product_id'],
                ip_address=get_client_ip(request),
            )
        except QuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TravelQuoteDetailSerializer(quote).data)


class TravelQuotePassengersView(APIView):
    """PUT /api/v1/quotes/travel/<uuid>/passengers/"""
    permission_classes = [IsAuthenticated]

    def put(self, request, quote_id):
        serializer = SaveQuotePassengersSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            quote = get_user_quote(user=request.user, quote_id=quote_id)
            quote = save_quote_passengers(
                quote=quote,
                passengers_data=serializer.validated_data['passengers'],
                ip_address=get_client_ip(request),
            )
        except QuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TravelQuoteDetailSerializer(quote).data)


class AutoQuoteListCreateView(APIView):
    """
    GET  /api/v1/quotes/auto/ — historial de cotizaciones de autos
    POST /api/v1/quotes/auto/ — nueva cotización Allianz Call4
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        include_expired = request.query_params.get('include_expired', '').lower() == 'true'
        quotes = list_user_auto_quotes(user=request.user, include_expired=include_expired)
        serializer = AutoQuoteListSerializer(quotes, many=True)
        return Response({'items': serializer.data})

    def post(self, request):
        serializer = AutoQuoteCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            quote = create_auto_quote(
                user=request.user,
                data=serializer.validated_data,
                ip_address=get_client_ip(request),
                correlation_id=request.META.get('CORRELATION_ID', ''),
            )
        except AutoQuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            AutoQuoteDetailSerializer(quote).data,
            status=status.HTTP_201_CREATED,
        )


class AutoQuoteDetailView(APIView):
    """GET /api/v1/quotes/auto/<uuid>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, quote_id):
        try:
            quote = get_user_auto_quote(user=request.user, quote_id=quote_id)
        except AutoQuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response(AutoQuoteDetailSerializer(quote).data)


class AutoQuoteSelectProductView(APIView):
    """POST /api/v1/quotes/auto/<uuid>/select-product/ — Lo quiero + comercial."""
    permission_classes = [IsAuthenticated]

    def post(self, request, quote_id):
        serializer = SelectProductSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            quote = get_user_auto_quote(user=request.user, quote_id=quote_id)
            quote = select_auto_quote_product(
                quote=quote,
                product_id=serializer.validated_data['product_id'],
                ip_address=get_client_ip(request),
            )
        except AutoQuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AutoQuoteDetailSerializer(quote).data)


class HomeQuoteListCreateView(APIView):
    """
    GET  /api/v1/quotes/home/ — historial de cotizaciones de hogar
    POST /api/v1/quotes/home/ — nueva cotización Allianz Hogar 2013
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        include_expired = request.query_params.get('include_expired', '').lower() == 'true'
        quotes = list_user_home_quotes(user=request.user, include_expired=include_expired)
        serializer = HomeQuoteListSerializer(quotes, many=True)
        return Response({'items': serializer.data})

    def post(self, request):
        serializer = HomeQuoteCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            quote = create_home_quote(
                user=request.user,
                data=serializer.validated_data,
                ip_address=get_client_ip(request),
                correlation_id=request.META.get('CORRELATION_ID', ''),
            )
        except HomeQuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            HomeQuoteDetailSerializer(quote).data,
            status=status.HTTP_201_CREATED,
        )


class HomeQuoteDetailView(APIView):
    """GET /api/v1/quotes/home/<uuid>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, quote_id):
        try:
            quote = get_user_home_quote(user=request.user, quote_id=quote_id)
        except HomeQuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response(HomeQuoteDetailSerializer(quote).data)


class HomeQuoteSelectProductView(APIView):
    """POST /api/v1/quotes/home/<uuid>/select-product/ — Lo quiero + comercial."""
    permission_classes = [IsAuthenticated]

    def post(self, request, quote_id):
        serializer = SelectProductSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            quote = get_user_home_quote(user=request.user, quote_id=quote_id)
            quote = select_home_quote_product(
                quote=quote,
                product_id=serializer.validated_data['product_id'],
                ip_address=get_client_ip(request),
            )
        except HomeQuoteServiceError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HomeQuoteDetailSerializer(quote).data)
