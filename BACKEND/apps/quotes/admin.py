from django.contrib import admin
from .models import QuoteProduct, QuoteProductAttribute, TravelQuote


class QuoteProductAttributeInline(admin.TabularInline):
    model = QuoteProductAttribute
    extra = 0


class QuoteProductInline(admin.TabularInline):
    model = QuoteProduct
    extra = 0
    show_change_link = True


@admin.register(TravelQuote)
class TravelQuoteAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'status', 'destination_siebel', 'passenger_count',
        'lead_id_siebel', 'expires_at', 'created_at',
    )
    list_filter = ('status', 'affiliate_type')
    search_fields = ('id', 'lead_id_siebel', 'user__email_primary')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [QuoteProductInline]


@admin.register(QuoteProduct)
class QuoteProductAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'quote', 'product_id_siebel', 'price_emission_local')
    search_fields = ('product_name', 'product_id_siebel')
    inlines = [QuoteProductAttributeInline]
