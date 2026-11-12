import io
import os
import urllib.parse
from datetime import datetime
from django.utils import timezone
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Sum, Count, Q
from rest_framework import generics, status, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def reshape_arabic(text):
        if not text:
            return ""
        try:
            return get_display(arabic_reshaper.reshape(str(text)))
        except Exception:
            return str(text)
except ImportError:
    def reshape_arabic(text):
        return str(text) if text else ""

from accounts.models import User
from accounts.permissions import IsAdminUser, IsDeputyOrAdmin, IsSuperAdminUser
from employees.models import Employee, RegisteredDevice
from organization.models import Worksite
from .models import AttendanceDay, AttendanceEvent, EmployeeRequest, AuditLog
from .pdf_generator import build_single_employee_pdf_buffer, build_master_attendance_pdf_buffer
from .utils import calculate_haversine_distance
from .serializers import (
    AttendanceEventSerializer,
    AttendanceRecordRequestSerializer,
    EmployeeRequestSerializer,
    EmployeeRequestDecisionSerializer,
    AuditLogSerializer
)


class AttendanceRecordEventView(APIView):
    """
    الـ API الجوهري لتسجيل الحضور والانصراف:
    - التحقق من تفعيل حساب الموظف ومنشأته.
    - التحقق من اعتماد الجهاز (Installation ID).
    - منع التكرار عبر Idempotency Key.
    - التحقق من النطاق الجغرافي (Geofencing) بدقة الـ GPS.
    - التوثيق بوقت الخادم المعتمد حصراً.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        # 1. التحقق من أن المستخدم موظف وحسابه نشط
        if not hasattr(user, 'employee_profile') or user.account_status != User.AccountStatus.ACTIVE:
            return Response({
                "detail": "حسابك غير مصرح له بتسجيل الحضور، تأكد من اعتماد وتفعيل حسابك من قبل الإدارة."
            }, status=status.HTTP_403_FORBIDDEN)

        employee = user.employee_profile

        # التحقق من أن منشأة الموظف نشطة
        if employee.organization and not employee.organization.is_active:
            return Response({
                "detail": "تم إيقاف نشاط المنشأة مؤقتاً، لا يمكن تسجيل الحضور حالياً (يرجى مراجعة إدارة المنشأة)."
            }, status=status.HTTP_403_FORBIDDEN)

        # 2. فحص صحة المدخلات
        serializer = AttendanceRecordRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 3. فحص مفتاح منع التكرار (Idempotency Key)
        idempotency_key = data['idempotency_key']
        existing_event = AttendanceEvent.objects.filter(idempotency_key=idempotency_key).first()
        if existing_event:
            return Response(
                AttendanceEventSerializer(existing_event).data,
                status=status.HTTP_200_OK
            )

        # 4. فحص الجهاز المستخدم
        device = RegisteredDevice.objects.filter(
            employee=employee,
            installation_id=data['installation_id']
        ).first()

        if not device or device.status != RegisteredDevice.DeviceStatus.ACTIVE:
            return Response({
                "detail": "هذا الجهاز غير معتمد لتسجيل الحضور، يرجى تقديم طلب اعتماد هاتف للمدير.",
                "verification_status": "REJECTED"
            }, status=status.HTTP_400_BAD_REQUEST)

        # 5. فحص موقع العمل والـ Geofence
        worksite = employee.assigned_worksite
        if not worksite and employee.organization:
            worksite = Worksite.objects.filter(organization=employee.organization, is_active=True).first()

        if not worksite:
            worksite = Worksite.objects.filter(is_active=True).first()

        distance_m = None
        verification_status = AttendanceEvent.VerificationStatus.ACCEPTED
        failure_reason = ""

        if worksite:
            distance_m = calculate_haversine_distance(
                data['latitude'],
                data['longitude'],
                worksite.latitude,
                worksite.longitude
            )

            # التحقق هل الموظف داخل النطاق المسموح
            if distance_m > worksite.radius_m:
                verification_status = AttendanceEvent.VerificationStatus.REJECTED
                failure_reason = f"أنت خارج نطاق موقع العمل المسموح ({worksite.name})، المسافة: {distance_m}م، النطاق المسموح: {worksite.radius_m}م."

        # فحص دقة الـ GPS
        accuracy = data.get('accuracy_m', 0)
        if accuracy > 100:
            verification_status = AttendanceEvent.VerificationStatus.REVIEW_REQUIRED
            failure_reason += " | إشارة الـ GPS ضعيفة وغير دقيقة (>100م)."

        # 6. فحص تسلسل الحركات ومنع تكرار تسجيل الحضور وراء بعض
        # إذا تم تسجيل الحركة أوفلاين، نعتمد تاريخ ووقت البصمة الفعلي المرسل من الجهاز
        client_dt = data.get('client_timestamp')
        if client_dt:
            today = timezone.localtime(client_dt).date()
        else:
            today = timezone.localdate()

        requested_type = data['event_type']
        actual_event_type = requested_type

        # آخر حركة مقبولة مسجلة للموظف اليوم
        last_accepted_event = AttendanceEvent.objects.filter(
            employee=employee,
            server_timestamp__date=today,
            verification_status=AttendanceEvent.VerificationStatus.ACCEPTED
        ).order_by('-server_timestamp').first()

        if last_accepted_event is None:
            # لم يسجل أي حركة حضور مقبولة اليوم -> أول حركة يجب أن تكون CHECK_IN
            if requested_type in [AttendanceEvent.EventType.CHECK_OUT, AttendanceEvent.EventType.BREAK_OUT]:
                return Response({
                    "detail": "لا يمكنك تسجيل الانصراف أو الاستراحة قبل تسجيل الحضور أولاً لهذا اليوم.",
                    "verification_status": "REJECTED"
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            last_type = last_accepted_event.event_type

            if last_type in [AttendanceEvent.EventType.CHECK_IN, AttendanceEvent.EventType.BREAK_IN]:
                # الموظف حاضر وعلى رأس عمله حالياً
                if requested_type == AttendanceEvent.EventType.CHECK_IN:
                    first_checkin = AttendanceEvent.objects.filter(
                        employee=employee,
                        server_timestamp__date=today,
                        event_type__in=[AttendanceEvent.EventType.CHECK_IN, AttendanceEvent.EventType.BREAK_IN],
                        verification_status=AttendanceEvent.VerificationStatus.ACCEPTED
                    ).order_by('server_timestamp').first()
                    time_str = timezone.localtime(first_checkin.server_timestamp).strftime('%I:%M %p') if first_checkin else ""
                    return Response({
                        "detail": f"أنت مسجل حضورك بالفعل لهذا اليوم (الساعة {time_str})! لا يمكنك تسجيل الحضور مجدداً وراء بعض. يمكنك تسجيل استراحة مؤقتة أو تسجيل انصراف.",
                        "verification_status": "ALREADY_CHECKED_IN"
                    }, status=status.HTTP_400_BAD_REQUEST)

            elif last_type == AttendanceEvent.EventType.BREAK_OUT:
                # الموظف في فترة استراحة مؤقتة
                if requested_type == AttendanceEvent.EventType.BREAK_OUT:
                    return Response({
                        "detail": "أنت في فترة استراحة مؤقتة بالفعل، يمكنك العودة لمتابعة العمل بالضغط على تسجيل حضور.",
                        "verification_status": "ALREADY_ON_BREAK"
                    }, status=status.HTTP_400_BAD_REQUEST)
                elif requested_type == AttendanceEvent.EventType.CHECK_IN:
                    # عودة من الاستراحة -> نسجلها كـ عودة من استراحة
                    actual_event_type = AttendanceEvent.EventType.BREAK_IN

            elif last_type == AttendanceEvent.EventType.CHECK_OUT:
                # الموظف سجل انصرافه وانتهى دوام اليوم
                return Response({
                    "detail": "لقد قمت بتسجيل الانصراف بالفعل لهذا اليوم، ولا يمكن تسجيل حركات أخرى.",
                    "verification_status": "ALREADY_CHECKED_OUT"
                }, status=status.HTTP_400_BAD_REQUEST)

        # 7. تحديث أو إنشاء سجل اليوم (AttendanceDay)
        # يصبح PRESENT فقط إذا كانت الحركة مقبولة نظامياً (وليست خارج النطاق)
        is_event_accepted = (verification_status == AttendanceEvent.VerificationStatus.ACCEPTED)
        attendance_day, created = AttendanceDay.objects.get_or_create(
            employee=employee,
            work_date=today,
            defaults={'day_status': AttendanceDay.DayStatus.PRESENT if is_event_accepted else AttendanceDay.DayStatus.ABSENT}
        )
        if not created and is_event_accepted and attendance_day.day_status != AttendanceDay.DayStatus.PRESENT:
            attendance_day.day_status = AttendanceDay.DayStatus.PRESENT
            attendance_day.save(update_fields=['day_status'])

        # 8. حفظ حركة الحضور / الانصراف
        event = AttendanceEvent.objects.create(
            employee=employee,
            device=device,
            worksite=worksite,
            attendance_day=attendance_day,
            event_type=actual_event_type,
            latitude=data['latitude'],
            longitude=data['longitude'],
            accuracy_m=accuracy,
            distance_m=distance_m,
            biometric_method=data.get('biometric_method', 'LOCAL_BIOMETRIC'),
            verification_status=verification_status,
            idempotency_key=idempotency_key,
            failure_reason=failure_reason
        )

        # إذا تم تسجيل الحركة أوفلاين، نحدث توقيت البصمة ليعكس وقت الحضور الفعلي
        if client_dt:
            AttendanceEvent.objects.filter(id=event.id).update(server_timestamp=client_dt)
            event.refresh_from_db()

        # احتساب وتحديث دقائق وساعات العمل الفعلية عند تسجيل الانصراف
        if actual_event_type == AttendanceEvent.EventType.CHECK_OUT and is_event_accepted:
            first_checkin = AttendanceEvent.objects.filter(
                employee=employee,
                server_timestamp__date=today,
                event_type__in=[AttendanceEvent.EventType.CHECK_IN, AttendanceEvent.EventType.BREAK_IN],
                verification_status=AttendanceEvent.VerificationStatus.ACCEPTED
            ).order_by('server_timestamp').first()
            if first_checkin and event.server_timestamp > first_checkin.server_timestamp:
                worked_duration = int((event.server_timestamp - first_checkin.server_timestamp).total_seconds() / 60)
                attendance_day.worked_minutes = max(0, worked_duration)
                attendance_day.save(update_fields=['worked_minutes'])

        response_status = status.HTTP_201_CREATED if is_event_accepted else status.HTTP_400_BAD_REQUEST

        # رسائل تأكيد مخصصة واضحة باللغة العربية
        if is_event_accepted:
            if actual_event_type == AttendanceEvent.EventType.BREAK_IN:
                success_msg = "أهلاً بك مجدداً، تم تسجيل عودتك من الاستراحة بنجاح ✅"
            elif actual_event_type == AttendanceEvent.EventType.BREAK_OUT:
                success_msg = "تم تسجيل بدء الاستراحة المؤقتة بنجاح ☕"
            elif actual_event_type == AttendanceEvent.EventType.CHECK_OUT:
                success_msg = "تم تسجيل انصرافك بنجاح، نتمنى لك وقتاً ممتعاً 👋"
            else:
                success_msg = "تم تسجيل حضورك واعتماده نظامياً بنجاح ✅"
        else:
            success_msg = failure_reason

        return Response({
            "detail": success_msg,
            "event": AttendanceEventSerializer(event).data
        }, status=response_status)


class EmployeeAttendanceHistoryView(generics.ListAPIView):
    """سجل حركات الحضور والانصراف الخاص بالموظف الحالي."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AttendanceEventSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'employee_profile'):
            return AttendanceEvent.objects.filter(employee=user.employee_profile).order_by('-server_timestamp')
        return AttendanceEvent.objects.none()


class EmployeeAttendanceSummaryView(APIView):
    """
    الملخص العملي لحضور الموظف:
    - إجمالي أيام الحضور الفعلي.
    - إجمالي أيام الغياب.
    - إجمالي أيام التأخير.
    - إجمالي ساعات العمل الفعلية.
    - تفاصيل الشهر الحالي وإحصائياته.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'employee_profile'):
            return Response({"detail": "المستخدم الحالي ليس موظفاً."}, status=status.HTTP_403_FORBIDDEN)

        employee = user.employee_profile
        today = timezone.localdate()
        year = int(request.query_params.get('year', today.year))
        month = int(request.query_params.get('month', today.month))

        # سجلات الأيام الإجمالية
        all_days = AttendanceDay.objects.filter(employee=employee)
        lifetime_present = all_days.filter(day_status=AttendanceDay.DayStatus.PRESENT).count()
        lifetime_late = all_days.filter(day_status=AttendanceDay.DayStatus.LATE).count()
        lifetime_absent = all_days.filter(day_status=AttendanceDay.DayStatus.ABSENT).count()
        lifetime_leave = all_days.filter(day_status=AttendanceDay.DayStatus.LEAVE).count()
        lifetime_minutes = all_days.aggregate(total=Sum('worked_minutes'))['total'] or 0

        # سجلات الشهر المحدد
        month_days = all_days.filter(work_date__year=year, work_date__month=month)
        month_present = month_days.filter(day_status=AttendanceDay.DayStatus.PRESENT).count()
        month_late = month_days.filter(day_status=AttendanceDay.DayStatus.LATE).count()
        month_absent = month_days.filter(day_status=AttendanceDay.DayStatus.ABSENT).count()
        month_leave = month_days.filter(day_status=AttendanceDay.DayStatus.LEAVE).count()
        month_minutes = month_days.aggregate(total=Sum('worked_minutes'))['total'] or 0

        # إجمالي حركات الحضور والانصراف
        total_check_ins = AttendanceEvent.objects.filter(
            employee=employee,
            event_type=AttendanceEvent.EventType.CHECK_IN,
            verification_status=AttendanceEvent.VerificationStatus.ACCEPTED
        ).count()
        total_check_outs = AttendanceEvent.objects.filter(
            employee=employee,
            event_type=AttendanceEvent.EventType.CHECK_OUT,
            verification_status=AttendanceEvent.VerificationStatus.ACCEPTED
        ).count()

        pending_requests_count = EmployeeRequest.objects.filter(
            employee=employee,
            status=EmployeeRequest.RequestStatus.PENDING
        ).count()

        return Response({
            "employee_id": str(employee.id),
            "employee_name": employee.full_name,
            "employee_code": employee.employee_code,
            "organization_name": employee.organization.name if employee.organization else None,
            "summary_period": f"{year}-{month:02d}",
            "period_stats": {
                "present_days": month_present,
                "late_days": month_late,
                "absent_days": month_absent,
                "leave_days": month_leave,
                "worked_hours": round(month_minutes / 60.0, 2),
                "total_days_recorded": month_days.count()
            },
            "lifetime_stats": {
                "total_present_days": lifetime_present + lifetime_late,
                "present_on_time": lifetime_present,
                "late_days": lifetime_late,
                "absent_days": lifetime_absent,
                "leave_days": lifetime_leave,
                "total_worked_hours": round(lifetime_minutes / 60.0, 2),
                "total_check_ins": total_check_ins,
                "total_check_outs": total_check_outs
            },
            "pending_requests_count": pending_requests_count
        }, status=status.HTTP_200_OK)


class AdminAttendanceRecordsView(generics.ListAPIView):
    """
    استعراض سجلات الحضور والانصراف للمدراء:
    - معزولة تماماً لكل منشأة.
    - فلترة حسب الموظف، التاريخ، الفترة الزمنية، نوع الحركة، أو الحالة.
    """
    permission_classes = [IsDeputyOrAdmin]
    serializer_class = AttendanceEventSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = AttendanceEvent.objects.select_related('employee__user', 'employee__organization', 'worksite', 'device').all()

        if not user.is_super_admin:
            org = user.organization
            if org:
                queryset = queryset.filter(employee__organization=org)
            else:
                queryset = queryset.none()

        employee_id = self.request.query_params.get('employee_id')
        date_param = self.request.query_params.get('date')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        status_param = self.request.query_params.get('status')
        event_type = self.request.query_params.get('event_type')

        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        if date_param:
            queryset = queryset.filter(server_timestamp__date=date_param)
        if start_date:
            queryset = queryset.filter(server_timestamp__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(server_timestamp__date__lte=end_date)
        if status_param:
            queryset = queryset.filter(verification_status=status_param)
        if event_type:
            queryset = queryset.filter(event_type=event_type)

        return queryset.order_by('-server_timestamp')


class AdminAttendanceRecordDecisionView(APIView):
    """
    مخصص للمدير:
    البت في حركات الحضور خارج النطاق (احتساب استثنائي أو تأكيد الرفض).
    POST /api/attendance/admin/records/<uuid:pk>/decide/
    """
    permission_classes = [IsDeputyOrAdmin]

    def post(self, request, pk):
        try:
            event = AttendanceEvent.objects.select_related(
                'employee__organization', 'employee__user', 'attendance_day'
            ).get(pk=pk)
        except AttendanceEvent.DoesNotExist:
            return Response({"detail": "سجل الحركة غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_super_admin:
            org = request.user.organization
            if not org or event.employee.organization != org:
                return Response({"detail": "السجل يتبع لموظف في منشأة أخرى."}, status=status.HTTP_403_FORBIDDEN)

        action = request.data.get('action', '').upper()
        comment = request.data.get('comment', '').strip()

        if action not in ['APPROVE', 'REJECT']:
            return Response({"detail": "الإجراء غير صالح، يجب أن يكون APPROVE أو REJECT."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            admin_name = request.user.full_name or "المدير"
            if action == 'APPROVE':
                event.verification_status = AttendanceEvent.VerificationStatus.ACCEPTED
                event.failure_reason = f"تم الاعتماد الاستثنائي من قبل {admin_name}"
                if comment:
                    event.failure_reason += f": {comment}"
                event.save()

                # تحديث حالة يوم الحضور إلى PRESENT
                if event.attendance_day:
                    event.attendance_day.day_status = AttendanceDay.DayStatus.PRESENT
                    event.attendance_day.save(update_fields=['day_status'])

                AuditLog.objects.create(
                    actor=request.user,
                    action="APPROVE_ATTENDANCE_EXCEPTION",
                    entity_type="AttendanceEvent",
                    entity_id=event.id,
                    details={
                        "employee_id": str(event.employee.id),
                        "employee_name": event.employee.full_name,
                        "event_type": event.event_type,
                        "comment": comment
                    }
                )

                return Response({
                    "detail": "تم احتساب الحركة واعتمادها استثنائياً بنجاح ✅",
                    "event": AttendanceEventSerializer(event).data
                }, status=status.HTTP_200_OK)

            else:
                event.verification_status = AttendanceEvent.VerificationStatus.REJECTED
                event.failure_reason = f"تم تأكيد رفض الحركة من قبل {admin_name}"
                if comment:
                    event.failure_reason += f": {comment}"
                event.save()

                AuditLog.objects.create(
                    actor=request.user,
                    action="REJECT_ATTENDANCE_EXCEPTION",
                    entity_type="AttendanceEvent",
                    entity_id=event.id,
                    details={
                        "employee_id": str(event.employee.id),
                        "employee_name": event.employee.full_name,
                        "event_type": event.event_type,
                        "comment": comment
                    }
                )

                return Response({
                    "detail": "تم تأكيد رفض الحركة.",
                    "event": AttendanceEventSerializer(event).data
                }, status=status.HTTP_200_OK)


class AdminAttendanceExportExcelView(APIView):
    """
    تصدير سجلات الحضور والانصراف كملف Excel (.xlsx) احترافي ومنسق:
    - يحتوي كافة التفاصيل الدقيقة للموظف وتوقيت البصمة والموقع وحالة القبول.
    """
    permission_classes = [IsDeputyOrAdmin]

    def get(self, request):
        user = request.user
        queryset = AttendanceEvent.objects.select_related(
            'employee__user', 'employee__organization', 'employee__department', 'worksite', 'device'
        ).all()

        if not user.is_super_admin:
            org = user.organization
            if org:
                queryset = queryset.filter(employee__organization=org)
            else:
                queryset = queryset.none()

        # تطبيق الفلاتر
        employee_id = request.query_params.get('employee_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        status_param = request.query_params.get('status')

        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        if start_date:
            queryset = queryset.filter(server_timestamp__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(server_timestamp__date__lte=end_date)
        if status_param:
            queryset = queryset.filter(verification_status=status_param)

        records = queryset.order_by('-server_timestamp')

        # إنشاء مصنف Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "سجل الحضور والانصراف"
        ws.views.sheetView[0].rightToLeft = True

        # تنسيق العنوان الرئيسي
        org_title = user.organization.name if user.organization else "جميع المنشآت"
        ws.merge_cells('A1:J1')
        title_cell = ws['A1']
        title_cell.value = f"تقرير سجلات الحضور والانصراف - {org_title}"
        title_cell.font = Font(name='Arial', size=16, bold=True, color='FFFFFF')
        title_cell.fill = PatternFill(start_color='1E3A8A', end_color='1E3A8A', fill_type='solid')
        title_cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 40

        # رؤوس الأعمدة
        headers = [
            'م', 'الرقم الوظيفي', 'اسم الموظف', 'المنشأة', 'القسم',
            'نوع الحركة', 'التاريخ والوقت', 'موقع العمل', 'حالة البصمة', 'المسافة (متر)'
        ]
        ws.append([])  # السطر 2 فارغ
        ws.append(headers)  # السطر 3

        header_font = Font(name='Arial', size=11, bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='2563EB', end_color='2563EB', fill_type='solid')
        border_side = Side(border_style='thin', color='D1D5DB')
        cell_border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=3, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = cell_border
        ws.row_dimensions[3].height = 28

        # تعبئة البيانات
        zebra_fill = PatternFill(start_color='F8FAFC', end_color='F8FAFC', fill_type='solid')
        for idx, event in enumerate(records, start=1):
            emp = event.employee
            row_data = [
                idx,
                emp.employee_code,
                emp.full_name,
                emp.organization.name if emp.organization else '-',
                emp.department.name if emp.department else '-',
                event.get_event_type_display(),
                timezone.localtime(event.server_timestamp).strftime('%Y-%m-%d %H:%M:%S'),
                event.worksite.name if event.worksite else '-',
                event.get_verification_status_display(),
                f"{event.distance_m} م" if event.distance_m is not None else '-'
            ]
            ws.append(row_data)
            row_idx = ws.max_row
            ws.row_dimensions[row_idx].height = 22

            is_even = (idx % 2 == 0)
            for col_idx in range(1, len(row_data) + 1):
                c = ws.cell(row=row_idx, column=col_idx)
                c.font = Font(name='Arial', size=10)
                c.border = cell_border
                c.alignment = Alignment(horizontal='center', vertical='center')
                if is_even:
                    c.fill = zebra_fill

        # ضبط عرض الأعمدة تلقائياً
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"attendance_report_{timezone.localdate()}.xlsx"
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class AdminAttendanceExportPdfView(APIView):
    """
    تصدير تقرير الحضور والانصراف كملف PDF رسمي مصمم وفق أرقى المعايير الحكومية والأكاديمية:
    - كشف الدوام البيومتري المعتمد • سجل الحضور والانصراف لموظف واحد (عند تحديد employee_id أو طلب الموظف لنفسه).
    - كشف الدوام البيومتري المعتمد • السجل العام لكافة موظفي المنشأة (عند طلب المدير تقرير المنشأة بالكامل).
    - تطبيق قواعد العطلات الرسمية: يوما الخميس والجمعة عطلة أسبوعية رسمية (وفي حال تسجيل بصمة فيهما يُحتسب دوام إضافي).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        employee_id = request.query_params.get('employee_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        today_str = timezone.localdate().strftime('%Y-%m-%d')

        # 1. إذا كان المستخدم موظفاً عادياً وليس مديراً -> يطبع فقط سجله الخاص
        if not (user.is_admin or user.is_deputy or user.is_super_admin):
            if not hasattr(user, 'employee_profile'):
                return Response(
                    {"detail": "ليس لديك ملف موظف لتصدير كشف الدوام الخاص بك."},
                    status=status.HTTP_403_FORBIDDEN
                )
            employee = user.employee_profile
            buffer = build_single_employee_pdf_buffer(employee, start_date=start_date, end_date=end_date)
            safe_name = employee.full_name.strip().replace(" ", "_")
            filename = f"كشف_دوام_{safe_name}.pdf"
            quoted_filename = urllib.parse.quote(filename)
            response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quoted_filename}'
            return response

        # 2. إذا كان المستخدم مديراً وحدد موظفاً بعينه -> تقرير الموظف المفصل
        if employee_id:
            emp_qs = Employee.objects.select_related('user', 'organization', 'department')
            if not user.is_super_admin:
                if user.organization:
                    emp_qs = emp_qs.filter(organization=user.organization)
                else:
                    return Response({"detail": "حسابك غير مرتبط بمنشأة محددة."}, status=status.HTTP_400_BAD_REQUEST)

            employee = emp_qs.filter(id=employee_id).first()
            if not employee:
                return Response({"detail": "الموظف المطلوب غير موجود أو لا يتبع لمنشأتك."}, status=status.HTTP_404_NOT_FOUND)

            buffer = build_single_employee_pdf_buffer(employee, start_date=start_date, end_date=end_date)
            safe_name = employee.full_name.strip().replace(" ", "_")
            filename = f"كشف_دوام_{safe_name}.pdf"
            quoted_filename = urllib.parse.quote(filename)
            response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quoted_filename}'
            return response

        # 3. إذا لم يحدد موظفاً -> تقرير المنشأة العام
        queryset = AttendanceEvent.objects.select_related(
            'employee__user', 'employee__organization', 'employee__department', 'worksite'
        ).all()

        if not user.is_super_admin:
            org = user.organization
            if org:
                queryset = queryset.filter(employee__organization=org)
            else:
                queryset = queryset.none()
        else:
            org = user.organization

        if start_date:
            queryset = queryset.filter(server_timestamp__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(server_timestamp__date__lte=end_date)
        status_param = request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(verification_status=status_param)

        records_qs = queryset.order_by('-server_timestamp')
        buffer = build_master_attendance_pdf_buffer(org, records_qs, start_date=start_date, end_date=end_date)
        filename = "سجل_نشاط_الموظفين.pdf"
        quoted_filename = urllib.parse.quote(filename)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quoted_filename}'
        return response


class EmployeeRequestViewSet(viewsets.ModelViewSet):
    """تقديم ومتابعة طلبات الموظفين (مغادرة، إجازة، تصحيح، تغيير جهاز)."""
    serializer_class = EmployeeRequestSerializer

    def get_permissions(self):
        if self.action in ['decide']:
            return [IsDeputyOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin or user.is_deputy:
            queryset = EmployeeRequest.objects.select_related('employee__user', 'decided_by').all()
            if not user.is_super_admin:
                org = user.organization
                if org:
                    queryset = queryset.filter(employee__organization=org)
                else:
                    queryset = queryset.none()
            return queryset
        if hasattr(user, 'employee_profile'):
            return EmployeeRequest.objects.filter(employee=user.employee_profile)
        return EmployeeRequest.objects.none()

    def perform_create(self, serializer):
        serializer.save(
            employee=self.request.user.employee_profile,
            status=EmployeeRequest.RequestStatus.PENDING
        )

    def decide(self, request, pk=None):
        """اتخاذ قرار بالقبول أو الرفض من قبل المدير."""
        emp_request = self.get_object()
        serializer = EmployeeRequestDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        emp_request.status = serializer.validated_data['status']
        emp_request.manager_comment = serializer.validated_data.get('manager_comment', '')
        emp_request.decided_by = request.user
        emp_request.decided_at = timezone.now()
        emp_request.save()

        # تسجيل العملية في الـ Audit Log
        AuditLog.objects.create(
            actor=request.user,
            action=f"DECIDE_REQUEST_{emp_request.status}",
            entity_type="EmployeeRequest",
            entity_id=emp_request.id,
            details={
                "employee_code": emp_request.employee.employee_code,
                "request_type": emp_request.request_type,
                "comment": emp_request.manager_comment
            }
        )

        return Response({
            "detail": f"تم تسجيل القرار بنجاح: {emp_request.get_status_display()}"
        }, status=status.HTTP_200_OK)


class DashboardStatsView(APIView):
    """إحصائيات فورية للوحة تحكم المدير (Dashboard) معزولة لكل منشأة."""
    permission_classes = [IsDeputyOrAdmin]

    def get(self, request):
        user = request.user
        today = timezone.localdate()

        emp_qs = Employee.objects.all()
        att_qs = AttendanceDay.objects.all()
        req_qs = EmployeeRequest.objects.all()
        dev_qs = RegisteredDevice.objects.all()
        user_qs = User.objects.filter(role=User.Role.EMPLOYEE)

        if not user.is_super_admin:
            org = user.organization
            if org:
                emp_qs = emp_qs.filter(organization=org)
                att_qs = att_qs.filter(employee__organization=org)
                req_qs = req_qs.filter(employee__organization=org)
                dev_qs = dev_qs.filter(employee__organization=org)
                user_qs = user_qs.filter(employee_profile__organization=org)
            else:
                emp_qs = emp_qs.none()
                att_qs = att_qs.none()
                req_qs = req_qs.none()
                dev_qs = dev_qs.none()
                user_qs = user_qs.none()

        total_employees = emp_qs.filter(is_active=True).count()
        present_today = att_qs.filter(work_date=today, day_status=AttendanceDay.DayStatus.PRESENT).count()
        late_today = att_qs.filter(work_date=today, day_status=AttendanceDay.DayStatus.LATE).count()
        pending_requests = req_qs.filter(status=EmployeeRequest.RequestStatus.PENDING).count()
        pending_devices = dev_qs.filter(status=RegisteredDevice.DeviceStatus.PENDING).count()
        pending_employees = user_qs.filter(account_status=User.AccountStatus.PENDING).count()

        return Response({
            "date": today,
            "organization_name": user.organization.name if user.organization else "جميع المنشآت",
            "total_employees": total_employees,
            "present_today": present_today,
            "late_today": late_today,
            "absent_today": max(0, total_employees - present_today - late_today),
            "pending_requests": pending_requests,
            "pending_devices": pending_devices,
            "pending_employee_accounts": pending_employees,
        }, status=status.HTTP_200_OK)


class AdminAuditLogsView(generics.ListAPIView):
    """استعراض سجل الرقابة والتدقيق (مخصص للسوبر أدمن والمدراء)."""
    permission_classes = [IsDeputyOrAdmin]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = AuditLog.objects.select_related('actor').all()
        if not user.is_super_admin:
            # فلترة بالمدير الحالي أو مستخدمي منشأته
            org = user.organization
            if org:
                queryset = queryset.filter(
                    Q(actor=user) | Q(actor__employee_profile__organization=org) | Q(actor__created_by=user)
                )
            else:
                queryset = queryset.none()
        return queryset.order_by('-created_at')
