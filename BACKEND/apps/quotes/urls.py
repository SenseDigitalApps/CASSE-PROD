from django.urls import path
from .views import (
    TravelQuoteDetailView,
    TravelQuoteListCreateView,
    TravelQuotePassengersView,
    TravelQuoteRequoteView,
    TravelQuoteSelectProductView,
)

urlpatterns = [
    path('travel/', TravelQuoteListCreateView.as_view(), name='travel-quote-list-create'),
    path('travel/<uuid:quote_id>/', TravelQuoteDetailView.as_view(), name='travel-quote-detail'),
    path(
        'travel/<uuid:quote_id>/requote/',
        TravelQuoteRequoteView.as_view(),
        name='travel-quote-requote',
    ),
    path(
        'travel/<uuid:quote_id>/select-product/',
        TravelQuoteSelectProductView.as_view(),
        name='travel-quote-select-product',
    ),
    path(
        'travel/<uuid:quote_id>/passengers/',
        TravelQuotePassengersView.as_view(),
        name='travel-quote-passengers',
    ),
]
