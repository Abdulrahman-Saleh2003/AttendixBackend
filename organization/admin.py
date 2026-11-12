from django.contrib import admin
from .models import Organization, Department, Worksite, Shift


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'admin', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'admin__full_name', 'admin__email')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'code', 'is_active', 'created_at')
    list_filter = ('is_active', 'organization')
    search_fields = ('name', 'code')


@admin.register(Worksite)
class WorksiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'latitude', 'longitude', 'radius_m', 'is_active', 'created_at')
    list_filter = ('is_active', 'organization')
    search_fields = ('name', 'address')


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'start_time', 'end_time', 'grace_minutes', 'working_days', 'is_active')
    list_filter = ('is_active', 'organization')
    search_fields = ('name',)
