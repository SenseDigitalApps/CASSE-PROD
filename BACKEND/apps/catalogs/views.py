"""Catalog API views for frontend dropdowns."""
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogs.models import CatalogEntry, DestinationMapping
from apps.catalogs.serializers import CatalogEntrySerializer, DestinationMappingSerializer


class CatalogListView(APIView):
    """
    GET /api/v1/catalogs/<catalog_type>/
    Returns active LOV entries for a given catalog type.
    """
    permission_classes = [AllowAny]

    VALID_TYPES = {choice.value for choice in CatalogEntry.CatalogType}

    def get(self, request, catalog_type: str):
        catalog_type = catalog_type.upper().replace('-', '_')
        if catalog_type not in self.VALID_TYPES:
            return Response(
                {'detail': f'Tipo de catálogo inválido: {catalog_type}'},
                status=400,
            )

        entries = CatalogEntry.objects.filter(
            catalog_type=catalog_type,
            is_active=True,
        )
        serializer = CatalogEntrySerializer(entries, many=True)
        return Response({
            'catalog_type': catalog_type,
            'items': serializer.data,
        })


class DestinationMappingListView(APIView):
    """GET /api/v1/catalogs/destinations/mappings/"""
    permission_classes = [AllowAny]

    def get(self, request):
        mappings = DestinationMapping.objects.filter(is_active=True)
        serializer = DestinationMappingSerializer(mappings, many=True)
        return Response({'items': serializer.data})


class CatalogIndexView(APIView):
    """GET /api/v1/catalogs/ — list available catalog types."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'catalog_types': [
                {'type': choice.value, 'label': choice.label}
                for choice in CatalogEntry.CatalogType
            ],
            'endpoints': {
                'destinations': '/api/v1/catalogs/DESTINATION/',
                'trip_types': '/api/v1/catalogs/TRIP_TYPE/',
                'document_types': '/api/v1/catalogs/DOCUMENT_TYPE/',
                'destination_mappings': '/api/v1/catalogs/destinations/mappings/',
            },
        })
