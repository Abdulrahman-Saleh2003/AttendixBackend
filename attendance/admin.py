from django.contrib import admin
from .models import AttendanceDay, AttendanceEvent, EmployeeRequest, AttendanceCorrection, AuditLog


@admin.register(AttendanceDay)
class AttendanceDayAdmin(admin.ModelAdmin):
    list_display = ('employee', 'work_date', 'day_status', 'worked_minutes')
    list_filter = ('day_status', 'work_date')
    search_fields = ('employee__user__full_name', 'employee__employee_code')


@admin.register(AttendanceEvent)
class AttendanceEventAdmin(admin.ModelAdmin):
    list_display = ('employee', 'event_type', 'server_timestamp', 'distance_m', 'verification_status', 'accuracy_m')
    list_filter = ('event_type', 'verification_status', 'worksite')
    search_fields = ('employee__user__full_name', 'employee__employee_code', 'idempotency_key')
    readonly_fields = ('server_timestamp', 'idempotency_key')


@admin.register(EmployeeRequest)
class EmployeeRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'request_type', 'status', 'requested_at', 'decided_by')
    list_filter = ('request_type', 'status')
    search_fields = ('employee__user__full_name', 'employee__employee_code')


@admin.register(AttendanceCorrection)
class AttendanceCorrectionAdmin(admin.ModelAdmin):
    list_display = ('request', 'original_event', 'proposed_timestamp', 'approved_timestamp', 'approved_by')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'entity_type', 'entity_id', 'ip_address')
    list_filter = ('action', 'entity_type')
    search_fields = ('actor__email', 'action', 'entity_type')
    readonly_fields = ('created_at', 'actor', 'action', 'entity_type', 'entity_id', 'details', 'ip_address')
