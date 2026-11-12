import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from employees.models import Employee, RegisteredDevice
from organization.models import Worksite


class AttendanceDay(models.Model):
    """ملخص يوم الحضور للموظف وساعات العمل المحتسبة."""

    class DayStatus(models.TextChoices):
        PRESENT = 'PRESENT', _('حاضر')
        LATE = 'LATE', _('متأخر')
        ABSENT = 'ABSENT', _('غائب')
        LEAVE = 'LEAVE', _('إجازة رسمية / معتمدة')
        HOLIDAY = 'HOLIDAY', _('عطلة نهاية أسبوع / رسمية')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='attendance_days',
        verbose_name=_('الموظف')
    )
    work_date = models.DateField(_('تاريخ العمل'), db_index=True)
    day_status = models.CharField(
        _('حالة اليوم'),
        max_length=20,
        choices=DayStatus.choices,
        default=DayStatus.ABSENT
    )
    worked_minutes = models.PositiveIntegerField(_('إجمالي دقائق العمل المحتسبة'), default=0)

    class Meta:
        verbose_name = _('يوم حضور')
        verbose_name_plural = _('أيام الحضور')
        unique_together = ('employee', 'work_date')
        ordering = ['-work_date']

    def __str__(self):
        return f"{self.employee.full_name} - {self.work_date} ({self.get_day_status_display()})"


class AttendanceEvent(models.Model):
    """سجل حركة الحضور أو الانصراف اللحظية بوقت الخادم وإحداثيات GPS."""

    class EventType(models.TextChoices):
        CHECK_IN = 'CHECK_IN', _('تسجيل حضور')
        CHECK_OUT = 'CHECK_OUT', _('تسجيل انصراف')
        BREAK_OUT = 'BREAK_OUT', _('خروج استراحة مؤقت')
        BREAK_IN = 'BREAK_IN', _('عودة من استراحة')

    class VerificationStatus(models.TextChoices):
        ACCEPTED = 'ACCEPTED', _('مقبول ومعتمد')
        REJECTED = 'REJECTED', _('مرفوض')
        REVIEW_REQUIRED = 'REVIEW_REQUIRED', _('يحتاج مراجعة إدارية')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='attendance_events',
        verbose_name=_('الموظف')
    )
    device = models.ForeignKey(
        RegisteredDevice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events',
        verbose_name=_('الجهاز المستخدم')
    )
    worksite = models.ForeignKey(
        Worksite,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events',
        verbose_name=_('موقع العمل المعتمد')
    )
    attendance_day = models.ForeignKey(
        AttendanceDay,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events',
        verbose_name=_('يوم العمل')
    )

    event_type = models.CharField(
        _('نوع الحركة'),
        max_length=20,
        choices=EventType.choices,
        db_index=True
    )
    server_timestamp = models.DateTimeField(_('توقيت الخادم المعتمد'), auto_now_add=True, db_index=True)
    
    latitude = models.DecimalField(_('خط العرض الفعلي'), max_digits=10, decimal_places=7)
    longitude = models.DecimalField(_('خط الطول الفعلي'), max_digits=10, decimal_places=7)
    accuracy_m = models.PositiveIntegerField(_('دقة الـ GPS بالأمتار'), default=0)
    distance_m = models.DecimalField(
        _('المسافة عن موقع العمل (متر)'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    biometric_method = models.CharField(_('طريقة التحقق البيومتري'), max_length=50, default='LOCAL_BIOMETRIC')
    
    verification_status = models.CharField(
        _('حالة التحقق'),
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.ACCEPTED,
        db_index=True
    )
    
    idempotency_key = models.CharField(
        _('مفتاح منع التكرار (Idempotency Key)'),
        max_length=128,
        unique=True,
        db_index=True
    )
    failure_reason = models.CharField(_('سبب الرفض إن وجد'), max_length=255, blank=True)

    class Meta:
        verbose_name = _('حركة حضور وانصراف')
        verbose_name_plural = _('حركات الحضور والانصراف')
        ordering = ['-server_timestamp']

    def __str__(self):
        return f"{self.employee.full_name} - {self.get_event_type_display()} @ {self.server_timestamp.strftime('%Y-%m-%d %H:%M')}"


class EmployeeRequest(models.Model):
    """طلبات الموظف (مغادرة مبكرة، إجازة، تصحيح حضور، تغيير هاتف)."""

    class RequestType(models.TextChoices):
        EARLY_LEAVE = 'EARLY_LEAVE', _('مغادرة مبكرة')
        VACATION = 'VACATION', _('طلب إجازة')
        CORRECTION = 'CORRECTION', _('تصحيح حضور وانصراف')
        DEVICE_CHANGE = 'DEVICE_CHANGE', _('طلب تغيير الجهاز')

    class RequestStatus(models.TextChoices):
        PENDING = 'PENDING', _('قيد المراجعة')
        APPROVED = 'APPROVED', _('تمت الموافقة')
        REJECTED = 'REJECTED', _('مرفوض')
        CANCELLED = 'CANCELLED', _('ملغى من الموظف')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='requests',
        verbose_name=_('الموظف')
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decided_requests',
        verbose_name=_('متخذ القرار')
    )
    request_type = models.CharField(
        _('نوع الطلب'),
        max_length=30,
        choices=RequestType.choices,
        db_index=True
    )
    status = models.CharField(
        _('حالة الطلب'),
        max_length=20,
        choices=RequestStatus.choices,
        default=RequestStatus.PENDING,
        db_index=True
    )
    requested_at = models.DateTimeField(_('تاريخ تقديم الطلب'), auto_now_add=True)
    decided_at = models.DateTimeField(_('تاريخ اتخاذ القرار'), null=True, blank=True)
    reason = models.TextField(_('السبب والمبرر'))
    manager_comment = models.TextField(_('ملاحظات وتعليق المدير'), blank=True)
    request_data = models.JSONField(_('بيانات الطلب الإضافية'), default=dict, blank=True)

    class Meta:
        verbose_name = _('طلب موظف')
        verbose_name_plural = _('طلبات الموظفين')
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.employee.full_name} - {self.get_request_type_display()} ({self.get_status_display()})"


class AttendanceCorrection(models.Model):
    """سجل تصحيح حركة حضور معتمد دون حذف السجل الأصلي."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.OneToOneField(
        EmployeeRequest,
        on_delete=models.CASCADE,
        related_name='correction_detail',
        verbose_name=_('الطلب المرتبط')
    )
    original_event = models.ForeignKey(
        AttendanceEvent,
        on_delete=models.CASCADE,
        related_name='corrections',
        verbose_name=_('الحركة الأصلية')
    )
    proposed_timestamp = models.DateTimeField(_('الوقت المقترح من الموظف'))
    approved_timestamp = models.DateTimeField(_('الوقت المعتمد من المدير'), null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_corrections',
        verbose_name=_('اعتمد بواسطة')
    )

    class Meta:
        verbose_name = _('سجل تصحيح بصمة')
        verbose_name_plural = _('سجلات تصحيح البصمة')


class AuditLog(models.Model):
    """سجل رقابي وتدقيقي كامل لجميع العمليات الحساسة في النظام."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_actions',
        verbose_name=_('القائم بالعملية')
    )
    action = models.CharField(_('العملية'), max_length=100)
    entity_type = models.CharField(_('نوع العنصر'), max_length=100)
    entity_id = models.UUIDField(_('معرف العنصر'), null=True, blank=True)
    details = models.JSONField(_('تفاصيل العملية'), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_('عنوان الـ IP'), null=True, blank=True)
    created_at = models.DateTimeField(_('وقت العملية'), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('سجل تدقيق رقابي')
        verbose_name_plural = _('سجلات التدقيق الرقابي')
        ordering = ['-created_at']

    def __str__(self):
        actor_name = self.actor.full_name if self.actor else "System"
        return f"{self.created_at.strftime('%Y-%m-%d %H:%M')} | {actor_name} | {self.action} on {self.entity_type}"
