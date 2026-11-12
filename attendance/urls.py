from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AttendanceRecordEventView,
    EmployeeAttendanceHistoryView,
    EmployeeAttendanceSummaryView,
    AdminAttendanceRecordsView,
    AdminAttendanceRecordDecisionView,
    AdminAttendanceExportExcelView,
    AdminAttendanceExportPdfView,
    EmployeeRequestViewSet,
    DashboardStatsView,
    AdminAuditLogsView
)

app_name = 'attendance'

router = DefaultRouter()
router.register(r'requests', EmployeeRequestViewSet, basename='employee-request')

urlpatterns = [
    # حركات الحضور والانصراف للموظف
    path('record/', AttendanceRecordEventView.as_view(), name='record_attendance'),
    path('my-history/', EmployeeAttendanceHistoryView.as_view(), name='employee_history'),
    path('my-summary/', EmployeeAttendanceSummaryView.as_view(), name='employee_summary'),

    # استعراض السجلات وتصدير التقارير للإدارة والبت في الحركات خارج النطاق
    path('admin/records/', AdminAttendanceRecordsView.as_view(), name='admin_records'),
    path('admin/records/<uuid:pk>/decide/', AdminAttendanceRecordDecisionView.as_view(), name='admin_record_decide'),
    path('admin/export/excel/', AdminAttendanceExportExcelView.as_view(), name='admin_export_excel'),
    path('admin/export/pdf/', AdminAttendanceExportPdfView.as_view(), name='admin_export_pdf'),
    path('admin/dashboard-stats/', DashboardStatsView.as_view(), name='admin_dashboard_stats'),
    path('admin/audit-logs/', AdminAuditLogsView.as_view(), name='admin_audit_logs'),

    # البت في طلبات الموظفين (موافقة / رفض)
    path('requests/<uuid:pk>/decide/', EmployeeRequestViewSet.as_view({'post': 'decide'}), name='request_decide'),

    # مسارات الطلبات العامة
    path('', include(router.urls)),
]
