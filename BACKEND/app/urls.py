"""
URL configuration for app project.
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

@require_http_methods(["GET"])
def root_view(request):
    """
    Root endpoint that provides API information.
    """
    return JsonResponse({
        "service": "insurance-backend",
        "version": "v1",
        "status": "running",
        "endpoints": {
            "health": "/api/v1/health/",
            "admin": "/admin/",
            "auth": {
                "register": "/api/v1/auth/register/",
                "login": "/api/v1/auth/login/",
                "refresh": "/api/v1/auth/jwt/refresh/"
            },
            "users": {
                "me": "/api/v1/users/me/",
                "list": "/api/v1/users/",
                "detail": "/api/v1/users/{id}/"
            },
            "catalogs": {
                "index": "/api/v1/catalogs/",
                "destinations": "/api/v1/catalogs/DESTINATION/",
                "trip_types": "/api/v1/catalogs/TRIP_TYPE/",
                "mappings": "/api/v1/catalogs/destinations/mappings/"
            },
            "quotes": {
                "travel_list": "/api/v1/quotes/travel/",
                "travel_detail": "/api/v1/quotes/travel/{id}/",
                "travel_requote": "/api/v1/quotes/travel/{id}/requote/",
                "travel_select": "/api/v1/quotes/travel/{id}/select-product/",
                "travel_passengers": "/api/v1/quotes/travel/{id}/passengers/"
            },
            "payments": {
                "initiate": "/api/v1/payments/travel-quotes/{quote_id}/initiate/",
                "detail": "/api/v1/payments/{id}/",
                "confirm": "/api/v1/payments/{id}/confirm/"
            },
            "vouchers": {
                "issue": "/api/v1/vouchers/issue/",
                "detail": "/api/v1/vouchers/{id}/",
                "pdf": "/api/v1/vouchers/{id}/pdf/"
            }
        },
        "documentation": "See API_DOCUMENTATION.md for detailed API documentation"
    })

urlpatterns = [
    path('', root_view, name='root'),
    path('admin/', admin.site.urls),
    path('api/v1/health/', include('apps.health.urls')),
    path('api/v1/auth/', include('apps.authn.urls')),
    path('api/v1/users/', include('apps.users.urls')),
    path('api/v1/catalogs/', include('apps.catalogs.urls')),
    path('api/v1/quotes/', include('apps.quotes.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/v1/vouchers/', include('apps.vouchers.urls')),
    #Vista para la autenticación del usuario por medio de JWT

    path("auth/", include("apps.authn.urls")),
]

