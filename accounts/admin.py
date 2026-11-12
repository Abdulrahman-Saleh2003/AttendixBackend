from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ('email', 'full_name', 'role', 'account_status', 'is_active', 'created_at')
    list_filter = ('role', 'account_status', 'is_active')
    search_fields = ('email', 'full_name', 'phone')
    ordering = ('-created_at',)

    fieldsets = (
        ('معلومات الحساب', {'fields': ('email', 'password')}),
        ('البيانات الشخصية', {'fields': ('full_name', 'phone')}),
        ('الدور والحالة', {'fields': ('role', 'account_status', 'created_by')}),
        ('الصلاحيات', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('التواريخ', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )

    readonly_fields = ('created_at', 'updated_at', 'last_login')

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'role', 'password', 'is_active', 'is_staff'),
        }),
    )
