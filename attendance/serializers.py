from rest_framework import serializers
from django.utils import timezone
from organization.models import Shift
from .models import AttendanceDay, AttendanceEvent, EmployeeRequest, AttendanceCorrection, AuditLog


class AttendanceEventSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    verification_status_display = serializers.CharField(source='get_verification_status_display', read_only=True)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    employee_code = serializers.CharField(source='employee.employee_code', read_only=True)
    worksite_name = serializers.CharField(source='worksite.name', read_only=True)

    # حقول احتساب ساعات الدوام الفعلي والتلوين التنبيهي للأدمن
    worked_minutes = serializers.SerializerMethodField()
    worked_duration_display = serializers.SerializerMethodField()
    duration_status = serializers.SerializerMethodField()
    duration_status_display = serializers.SerializerMethodField()
    status_color = serializers.SerializerMethodField()
    shift_summary = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceEvent
        fields = [
            'id', 'employee', 'employee_name', 'employee_code', 'event_type',
            'event_type_display', 'server_timestamp', 'latitude', 'longitude',
            'accuracy_m', 'distance_m', 'worksite_name', 'verification_status',
            'verification_status_display', 'failure_reason', 'idempotency_key',
            'worked_minutes', 'worked_duration_display', 'duration_status',
            'duration_status_display', 'status_color', 'shift_summary'
        ]
        read_only_fields = ['id', 'server_timestamp', 'distance_m', 'verification_status', 'failure_reason']

    def _get_day_duration_metrics(self, obj):
        if hasattr(obj, '_cached_duration_metrics'):
            return obj._cached_duration_metrics

        event_date = obj.server_timestamp.date()
        events = AttendanceEvent.objects.filter(
            employee=obj.employee,
            server_timestamp__date=event_date,
            verification_status=AttendanceEvent.VerificationStatus.ACCEPTED
        ).order_by('server_timestamp')

        first_check_in = None
        last_check_out = None
        for ev in events:
            if ev.event_type in [AttendanceEvent.EventType.CHECK_IN, AttendanceEvent.EventType.BREAK_IN] and not first_check_in:
                first_check_in = ev.server_timestamp
            elif ev.event_type == AttendanceEvent.EventType.CHECK_OUT:
                last_check_out = ev.server_timestamp

        org = obj.employee.organization
        shift_duration_mins = 480
        shift_str = "08:00 ص - 04:00 م (8 ساعات)"
        tolerance_mins = 25
        if org:
            shift = Shift.objects.filter(organization=org, is_active=True).first()
            if shift:
                from datetime import datetime, date
                dt_start = datetime.combine(date.today(), shift.start_time)
                dt_end = datetime.combine(date.today(), shift.end_time)
                shift_duration_mins = max(60, int((dt_end - dt_start).total_seconds() / 60))
                tolerance_mins = shift.grace_minutes if shift.grace_minutes >= 15 else 25
                start_fmt = shift.start_time.strftime('%I:%M %p').replace('AM', 'ص').replace('PM', 'م')
                end_fmt = shift.end_time.strftime('%I:%M %p').replace('AM', 'ص').replace('PM', 'م')
                shift_str = f"{start_fmt} - {end_fmt} ({shift_duration_mins // 60} ساعات)"

        # إذا كانت الحركة الحالية مرفوضة أو خارج النطاق
        if obj.verification_status != AttendanceEvent.VerificationStatus.ACCEPTED:
            metrics = {
                'worked_minutes': 0,
                'worked_duration_display': 'خارج النطاق',
                'duration_status': 'OUT_OF_BOUNDS',
                'duration_status_display': 'خارج النطاق (غير محسوب)',
                'status_color': 'RED',
                'shift_summary': shift_str
            }
            obj._cached_duration_metrics = metrics
            return metrics

        if first_check_in and last_check_out and last_check_out > first_check_in:
            duration_mins = int((last_check_out - first_check_in).total_seconds() / 60)
            hours = duration_mins // 60
            mins = duration_mins % 60
            dur_display = f"{hours} ساعة و {mins} دقيقة" if hours > 0 else f"{mins} دقيقة"

            # تصنيف الحالة بالألوان بحسب توجيه المستخدم:
            # 🟢 دوام كامل: كامل الوقت أو أقل بربع إلى ثلث ساعة
            if duration_mins >= (shift_duration_mins - tolerance_mins):
                status_key = 'FULL_DAY'
                status_display = 'دوام رسمي كامل'
                color = 'GREEN'
            # 🟠 دوام أقل من الرسمي: داوم أكثر من نصف الدوام (مثلاً 5 ساعات فأكثر)
            elif duration_mins >= int(shift_duration_mins * 0.6):
                status_key = 'PARTIAL_DAY'
                status_display = 'دوام أقل من الرسمي (مغادرة مبكرة)'
                color = 'ORANGE'
            # 🟡 دوام قصير: حضر ثم خرج بعد فترة وجيزة (ساعات غير كافية)
            elif duration_mins >= 15:
                status_key = 'SHORT_DAY'
                status_display = 'دوام قصير (ساعات غير كافية)'
                color = 'YELLOW'
            # 🔴 انصراف فوري أقل من 15 دقيقة: غياب تام
            else:
                status_key = 'ABSENT'
                status_display = 'انصراف فوري / غير محسوب'
                color = 'RED'
        elif first_check_in and not last_check_out:
            is_today = (event_date == timezone.localdate())
            if is_today:
                now = timezone.now()
                dur_now = max(0, int((now - first_check_in).total_seconds() / 60))
                hours = dur_now // 60
                mins = dur_now % 60
                dur_display = f"{hours} س و {mins} د (على رأس عمله)"
                status_key = 'ON_DUTY'
                status_display = 'حاضر (قيد الدوام)'
                color = 'BLUE'
                duration_mins = dur_now
            else:
                dur_display = 'لم يسجل انصراف'
                status_key = 'INCOMPLETE'
                status_display = 'غير مكتمل (لم يسجل انصراف)'
                color = 'RED'
                duration_mins = 0
        else:
            duration_mins = 0
            dur_display = '0 دقيقة'
            status_key = 'ABSENT'
            status_display = 'غياب'
            color = 'RED'

        metrics = {
            'worked_minutes': duration_mins,
            'worked_duration_display': dur_display,
            'duration_status': status_key,
            'duration_status_display': status_display,
            'status_color': color,
            'shift_summary': shift_str
        }
        obj._cached_duration_metrics = metrics
        return metrics

    def get_worked_minutes(self, obj):
        return self._get_day_duration_metrics(obj)['worked_minutes']

    def get_worked_duration_display(self, obj):
        return self._get_day_duration_metrics(obj)['worked_duration_display']

    def get_duration_status(self, obj):
        return self._get_day_duration_metrics(obj)['duration_status']

    def get_duration_status_display(self, obj):
        return self._get_day_duration_metrics(obj)['duration_status_display']

    def get_status_color(self, obj):
        return self._get_day_duration_metrics(obj)['status_color']

    def get_shift_summary(self, obj):
        return self._get_day_duration_metrics(obj)['shift_summary']


class AttendanceRecordRequestSerializer(serializers.Serializer):
    """البيانات المرسلة من تطبيق الجوال لتسجيل الحضور أو الانصراف."""
    event_type = serializers.ChoiceField(choices=AttendanceEvent.EventType.choices)
    installation_id = serializers.CharField(required=True, max_length=255)
    latitude = serializers.DecimalField(required=True, max_digits=10, decimal_places=7)
    longitude = serializers.DecimalField(required=True, max_digits=10, decimal_places=7)
    accuracy_m = serializers.IntegerField(required=False, default=15)
    biometric_method = serializers.CharField(required=False, default='LOCAL_BIOMETRIC')
    idempotency_key = serializers.CharField(required=True, max_length=128)
    client_timestamp = serializers.DateTimeField(required=False, allow_null=True)


class EmployeeRequestSerializer(serializers.ModelSerializer):
    """عرض وتقديم طلبات الموظفين."""
    request_type_display = serializers.CharField(source='get_request_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    decided_by_name = serializers.CharField(source='decided_by.full_name', read_only=True)

    class Meta:
        model = EmployeeRequest
        fields = [
            'id', 'employee', 'employee_name', 'request_type', 'request_type_display',
            'status', 'status_display', 'reason', 'manager_comment', 'request_data',
            'decided_by_name', 'requested_at', 'decided_at'
        ]
        read_only_fields = ['id', 'employee', 'status', 'manager_comment', 'decided_by_name', 'requested_at', 'decided_at']


class EmployeeRequestDecisionSerializer(serializers.Serializer):
    """قرار المدير على طلب الموظف."""
    status = serializers.ChoiceField(choices=[
        (EmployeeRequest.RequestStatus.APPROVED, 'موافقة'),
        (EmployeeRequest.RequestStatus.REJECTED, 'رفض')
    ])
    manager_comment = serializers.CharField(required=False, allow_blank=True)


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.full_name', read_only=True)
    actor_email = serializers.CharField(source='actor.email', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'actor_name', 'actor_email', 'action', 'entity_type',
            'entity_id', 'details', 'ip_address', 'created_at'
        ]
