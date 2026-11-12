import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from organization.models import Organization, Department, Worksite, Shift


class Employee(models.Model):
    """الملف الوظيفي للموظف المرتبط بحسابه ومنشأته."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='employee_profile',
        verbose_name=_('حساب المستخدم')
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        verbose_name=_('المنشأة التابع لها')
    )
    employee_code = models.CharField(_('الرقم الوظيفي'), max_length=50, unique=True, db_index=True)
    job_title = models.CharField(_('المسمى الوظيفي'), max_length=150, blank=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        verbose_name=_('القسم')
    )
    assigned_worksite = models.ForeignKey(
        Worksite,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_employees',
        verbose_name=_('موقع العمل الأساسي')
    )
    hire_date = models.DateField(_('تاريخ التعيين'), null=True, blank=True)
    is_active = models.BooleanField(_('على رأس عمله'), default=True)
    notes = models.TextField(_('ملاحظات إدارية'), blank=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)

    class Meta:
        verbose_name = _('موظف')
        verbose_name_plural = _('الموظفون')
        ordering = ['employee_code']

    def __str__(self):
        org_title = f" [{self.organization.name}]" if self.organization else " [غير منضم لمنشأة]"
        return f"{self.user.full_name} ({self.employee_code}){org_title}"

    @property
    def full_name(self):
        return self.user.full_name

    @property
    def email(self):
        return self.user.email

    @property
    def phone(self):
        return self.user.phone

    @property
    def active_device(self):
        return self.devices.filter(status=RegisteredDevice.DeviceStatus.ACTIVE).first()


class OrganizationJoinRequest(models.Model):
    """
    طلبات انضمام الموظفين الجدد إلى المنشآت (الأدمنات):
    - ينشئ الموظف حسابه أولاً.
    - تظهر له واجهة تحتوي جميع المنشآت وأكوادها.
    - يختار المنشأة ويرسل طلب الانضمام.
    - قاعدة صارمة: ممنوع إرسال طلب ثانٍ إذا كان هناك طلب معلق (PENDING)
      إلا إذا رفض الأدمن طلبه الحالي (REJECTED).
    """

    class RequestStatus(models.TextChoices):
        PENDING = 'PENDING', _('بانتظار موافقة الأدمن')
        APPROVED = 'APPROVED', _('تمت الموافقة والاعتماد')
        REJECTED = 'REJECTED', _('مرفوض')
        CANCELLED = 'CANCELLED', _('ملغى من الموظف')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='join_requests',
        verbose_name=_('الموظف')
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='join_requests',
        verbose_name=_('المنشأة المستهدفة')
    )
    status = models.CharField(
        _('حالة طلب الانضمام'),
        max_length=20,
        choices=RequestStatus.choices,
        default=RequestStatus.PENDING,
        db_index=True
    )
    notes = models.TextField(_('ملاحظة الموظف في الطلب'), blank=True)
    admin_comment = models.TextField(_('تعليق الأدمن عند القرار'), blank=True)
    requested_at = models.DateTimeField(_('تاريخ تقديم الطلب'), auto_now_add=True)
    decided_at = models.DateTimeField(_('تاريخ اتخاذ القرار'), null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decided_join_requests',
        verbose_name=_('الأدمن متخذ القرار')
    )

    class Meta:
        verbose_name = _('طلب انضمام لمنشأة')
        verbose_name_plural = _('طلبات الانضمام للمنشآت')
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.employee.full_name} -> {self.organization.name} ({self.get_status_display()})"


class RegisteredDevice(models.Model):
    """أجهزة الهواتف المعتمدة والمربوطة بالموظفين (Device Binding)."""

    class DeviceStatus(models.TextChoices):
        PENDING = 'PENDING', _('بانتظار الاعتماد')
        ACTIVE = 'ACTIVE', _('معتمد ونشط')
        REJECTED = 'REJECTED', _('مرفوض')
        REVOKED = 'REVOKED', _('ملغى / مسحوب الاعتماد')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='devices',
        verbose_name=_('الموظف')
    )
    installation_id = models.CharField(_('معرّف التثبيت الفريد'), max_length=255, unique=True, db_index=True)
    public_key = models.TextField(_('المفتاح العام المشفر للهاتف'), blank=True)
    manufacturer = models.CharField(_('الشركة المصنعة'), max_length=100, blank=True)
    model = models.CharField(_('موديل الهاتف'), max_length=100, blank=True)
    os_version = models.CharField(_('إصدار النظام'), max_length=100, blank=True)
    
    status = models.CharField(
        _('حالة اعتماد الجهاز'),
        max_length=20,
        choices=DeviceStatus.choices,
        default=DeviceStatus.PENDING,
        db_index=True
    )
    
    approved_at = models.DateTimeField(_('تاريخ الاعتماد'), null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_devices',
        verbose_name=_('اعتمد بواسطة')
    )
    revoked_at = models.DateTimeField(_('تاريخ إلغاء الاعتماد'), null=True, blank=True)
    created_at = models.DateTimeField(_('تاريخ التسجيل الأول'), auto_now_add=True)

    class Meta:
        verbose_name = _('جهاز مسجل')
        verbose_name_plural = _('الأجهزة المسجلة')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.manufacturer} {self.model} - {self.employee.full_name} ({self.get_status_display()})"


class EmployeeShiftAssignment(models.Model):
    """ربط الموظف بالورديات وفق فترات زمنية."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='shift_assignments',
        verbose_name=_('الموظف')
    )
    shift = models.ForeignKey(
        Shift,
        on_delete=models.CASCADE,
        related_name='assigned_employees',
        verbose_name=_('الوردية')
    )
    valid_from = models.DateField(_('سارية من تاريخ'))
    valid_to = models.DateField(_('سارية حتى تاريخ (اختياري)'), null=True, blank=True)

    class Meta:
        verbose_name = _('تعيين وردية لموظف')
        verbose_name_plural = _('تعيينات الورديات للموظفين')
        ordering = ['-valid_from']

    def __str__(self):
        return f"{self.employee.full_name} -> {self.shift.name}"
