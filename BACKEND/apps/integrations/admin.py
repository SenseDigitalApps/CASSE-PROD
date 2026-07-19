from django.contrib import admin
from .models import IntegrationCallLog


@admin.register(IntegrationCallLog)
class IntegrationCallLogAdmin(admin.ModelAdmin):
    list_display = ('service_name', 'operation', 'status', 'duration_ms', 'created_at')
    list_filter = ('service_name', 'status', 'operation')
    search_fields = ('correlation_id', 'error_message', 'operation')
    readonly_fields = (
        'id', 'service_name', 'operation', 'status', 'request_payload',
        'response_payload', 'error_message', 'duration_ms', 'correlation_id',
        'actor_user', 'created_at',
    )
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
