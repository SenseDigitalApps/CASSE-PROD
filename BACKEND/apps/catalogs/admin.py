from django.contrib import admin
from .models import CatalogEntry, DestinationMapping


@admin.register(CatalogEntry)
class CatalogEntryAdmin(admin.ModelAdmin):
    list_display = ('catalog_type', 'code', 'label', 'is_active', 'sort_order')
    list_filter = ('catalog_type', 'is_active')
    search_fields = ('code', 'label')


@admin.register(DestinationMapping)
class DestinationMappingAdmin(admin.ModelAdmin):
    list_display = ('ui_code', 'ui_label', 'siebel_value', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('ui_code', 'ui_label', 'siebel_value')
