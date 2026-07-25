from django.urls import path
from .views import (
    AutoQuoteDetailView,
    AutoQuoteListCreateView,
    AutoQuoteSelectProductView,
    HomeQuoteDetailView,
    HomeQuoteListCreateView,
    HomeQuoteSelectProductView,
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
    path('auto/', AutoQuoteListCreateView.as_view(), name='auto-quote-list-create'),
    path('auto/<uuid:quote_id>/', AutoQuoteDetailView.as_view(), name='auto-quote-detail'),
    path(
        'auto/<uuid:quote_id>/select-product/',
        AutoQuoteSelectProductView.as_view(),
        name='auto-quote-select-product',
    ),
    path('home/', HomeQuoteListCreateView.as_view(), name='home-quote-list-create'),
    path('home/<uuid:quote_id>/', HomeQuoteDetailView.as_view(), name='home-quote-detail'),
    path(
        'home/<uuid:quote_id>/select-product/',
        HomeQuoteSelectProductView.as_view(),
        name='home-quote-select-product',
    ),
]
