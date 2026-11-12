from django.contrib import admin
from .models import Employee, RegisteredDevice, EmployeeShiftAssignment, OrganizationJoinRequest


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_code', 'full_name', 'email', 'organization', 'department', 'assigned_worksite', 'is_active', 'created_at')
    list_filter = ('is_active', 'organization', 'department', 'assigned_worksite')
    search_fields = ('employee_code', 'user__full_name', 'user__email')


@admin.register(OrganizationJoinRequest)
class OrganizationJoinRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'organization', 'status', 'requested_at', 'decided_at', 'decided_by')
    list_filter = ('status', 'organization')
    search_fields = ('employee__user__full_name', 'employee__employee_code', 'organization__name', 'organization__code')
    readonly_fields = ('requested_at',)


@admin.register(RegisteredDevice)
class RegisteredDeviceAdmin(admin.ModelAdmin):
    list_display = ('installation_id', 'employee', 'manufacturer', 'model', 'status', 'approved_at', 'created_at')
    list_filter = ('status', 'manufacturer')
    search_fields = ('installation_id', 'employee__user__full_name', 'employee__employee_code')


@admin.register(EmployeeShiftAssignment)
class EmployeeShiftAssignmentAdmin(admin.ModelAdmin):
    list_display = ('employee', 'shift', 'valid_from', 'valid_to')
    list_filter = ('shift',)
    search_fields = ('employee__user__full_name', 'employee__employee_code')
