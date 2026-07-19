from django.urls import path
from .views import CatalogIndexView, CatalogListView, DestinationMappingListView

urlpatterns = [
    path('', CatalogIndexView.as_view(), name='catalog-index'),
    path('destinations/mappings/', DestinationMappingListView.as_view(), name='destination-mappings'),
    path('<str:catalog_type>/', CatalogListView.as_view(), name='catalog-list'),
]
