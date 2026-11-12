from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EmployeeRegisterView,
    EmployeeJoinRequestView,
    AdminJoinRequestsListView,
    AdminJoinRequestDecisionView,
    AdminEmployeeListView,
    AdminEmployeeDetailView,
    AdminEmployeeAddView,
    AdminEmployeeDeleteView,
    AdminEmployeeStatusUpdateView,
    DeviceRegisterView,
    AdminDeviceListView,
    AdminDeviceStatusUpdateView,
    AdminDeviceApproveView,
    AdminDeviceRejectView,
    AdminDeviceResetView,
    ShiftAssignmentViewSet
)

app_name = 'employees'

router = DefaultRouter()
router.register(r'shifts', ShiftAssignmentViewSet, basename='employee-shift')

urlpatterns = [
    # مسارات الموظف (الموبايل)
    path('register/', EmployeeRegisterView.as_view(), name='employee_register'),
    path('join-requests/', EmployeeJoinRequestView.as_view(), name='employee_join_requests'),
    path('devices/register/', DeviceRegisterView.as_view(), name='device_register'),

    # مسارات لوحة التحكم (المدير) — طلبات الانضمام
    path('admin/join-requests/', AdminJoinRequestsListView.as_view(), name='admin_join_requests_list'),
    path('admin/join-requests/<uuid:pk>/decide/', AdminJoinRequestDecisionView.as_view(), name='admin_join_request_decide'),

    # مسارات الموظفين
    path('admin/list/', AdminEmployeeListView.as_view(), name='admin_employee_list'),
    path('admin/add/', AdminEmployeeAddView.as_view(), name='admin_employee_add'),
    path('admin/<uuid:pk>/', AdminEmployeeDetailView.as_view(), name='admin_employee_detail'),
    path('admin/<uuid:pk>/delete/', AdminEmployeeDeleteView.as_view(), name='admin_employee_delete'),
    path('admin/<uuid:pk>/status/', AdminEmployeeStatusUpdateView.as_view(), name='admin_employee_status'),
    path('admin/<uuid:pk>/reset-device/', AdminDeviceResetView.as_view(), name='admin_device_reset'),

    # مسارات إدارة الأجهزة (Device Management)
    path('admin/devices/', AdminDeviceListView.as_view(), name='admin_device_list'),
    path('admin/devices/<uuid:pk>/status/', AdminDeviceStatusUpdateView.as_view(), name='admin_device_status'),
    path('admin/devices/<uuid:pk>/approve/', AdminDeviceApproveView.as_view(), name='admin_device_approve'),
    path('admin/devices/<uuid:pk>/reject/', AdminDeviceRejectView.as_view(), name='admin_device_reject'),

    # ربط الورديات
    path('', include(router.urls)),
]
