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
    #Vista para la autenticación del usuario por medio de JWT

    path("auth/", include("apps.authn.urls")),
]

