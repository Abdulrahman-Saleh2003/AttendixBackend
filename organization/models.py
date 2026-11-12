import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class Organization(models.Model):
    """
    المنشأة أو الشركة أو الفرع.
    لكل أدمن منشأة خاصة به، ولها كود فريد (Organization Code)
    يستخدمه الموظفون لاختيار منشأتهم والانضمام إليها.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_('اسم المنشأة / الشركة'), max_length=200)
    code = models.CharField(_('كود المنشأة الفريد'), max_length=50, unique=True, db_index=True)
    admin = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='managed_organization',
        verbose_name=_('الأدمن المسؤول')
    )
    is_active = models.BooleanField(_('نشطة'), default=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)

    class Meta:
        verbose_name = _('منشأة')
        verbose_name_plural = _('المنشآت')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Department(models.Model):
    """الأقسام الإدارية والتشغيلية في المؤسسة."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='departments',
        verbose_name=_('المنشأة')
    )
    name = models.CharField(_('اسم القسم'), max_length=150)
    code = models.CharField(_('رمز القسم'), max_length=50, blank=True, null=True)
    is_active = models.BooleanField(_('نشط'), default=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)

    class Meta:
        verbose_name = _('قسم')
        verbose_name_plural = _('الأقسام')
        ordering = ['name']

    def __str__(self):
        return self.name


class Worksite(models.Model):
    """مواقع العمل المعتمدة ونطاق الـ GPS الجغرافي (Geofencing)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='worksites',
        verbose_name=_('المنشأة')
    )
    name = models.CharField(_('اسم الموقع'), max_length=150)
    address = models.CharField(_('العنوان الوصفي'), max_length=255, blank=True)
    latitude = models.DecimalField(_('خط العرض (Latitude)'), max_digits=10, decimal_places=7)
    longitude = models.DecimalField(_('خط الطول (Longitude)'), max_digits=10, decimal_places=7)
    radius_m = models.PositiveIntegerField(_('نصف قطر النطاق المسموح (بالأمتار)'), default=100)
    is_active = models.BooleanField(_('موقع نشط'), default=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)

    class Meta:
        verbose_name = _('موقع عمل')
        verbose_name_plural = _('مواقع العمل')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (نطاق {self.radius_m}م)"


class Shift(models.Model):
    """الورديات ومواعيد الدوام المحددة."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='shifts',
        verbose_name=_('المنشأة')
    )
    name = models.CharField(_('اسم الوردية'), max_length=100)
    start_time = models.TimeField(_('وقت بدء الدوام'))
    end_time = models.TimeField(_('وقت نهاية الدوام'))
    grace_minutes = models.PositiveIntegerField(_('فترة السماح للتأخير (بالدقائق)'), default=15)
    working_days = models.CharField(
        _('أيام العمل'),
        max_length=100,
        default='Sun,Mon,Tue,Wed,Thu',
        help_text=_('مفصولة بفواصل، مثل: Sun,Mon,Tue,Wed,Thu')
    )
    is_active = models.BooleanField(_('وردية نشطة'), default=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)

    class Meta:
        verbose_name = _('وردية دوام')
        verbose_name_plural = _('ورديات الدوام')
        ordering = ['start_time']

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"
