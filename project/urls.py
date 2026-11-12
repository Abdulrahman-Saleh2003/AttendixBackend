"""
URL configuration for Attendix / بصمتي attendance management backend.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # لوحة إدارة دجانغو الأساسية
    path('admin/', admin.site.urls),

    # واجهات الـ REST API لجميع الوحدات
    path('api/accounts/', include('accounts.urls', namespace='accounts')),
    path('api/org/', include('organization.urls', namespace='organization')),
    path('api/employees/', include('employees.urls', namespace='employees')),
    path('api/attendance/', include('attendance.urls', namespace='attendance')),
]
