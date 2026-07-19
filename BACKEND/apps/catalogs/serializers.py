from rest_framework import serializers
from .models import CatalogEntry, DestinationMapping


class CatalogEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogEntry
        fields = ('code', 'label')


class DestinationMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = DestinationMapping
        fields = ('ui_code', 'ui_label', 'siebel_value')
