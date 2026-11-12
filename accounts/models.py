import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    """مدير مخصص لنموذج المستخدم يعتمد على البريد الإلكتروني كمعرف أساسي."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('يجب تقديم البريد الإلكتروني'))
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.SUPER_ADMIN)
        extra_fields.setdefault('account_status', User.AccountStatus.ACTIVE)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('يجب أن يكون is_staff=True لحساب السوبر أدمن.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('يجب أن يكون is_superuser=True لحساب السوبر أدمن.'))

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    النموذج الأساسي لجميع مستخدمي النظام:
    - السوبر أدمن (مالك النظام)
    - المدير (Admin)
    - نائب المدير (Deputy Admin)
    - الموظف (Employee)
    """

    class Role(models.TextChoices):
        SUPER_ADMIN = 'SUPER_ADMIN', _('سوبر أدمن (مالك النظام)')
        ADMIN = 'ADMIN', _('مدير')
        DEPUTY_ADMIN = 'DEPUTY_ADMIN', _('نائب مدير')
        EMPLOYEE = 'EMPLOYEE', _('موظف')

    class AccountStatus(models.TextChoices):
        PENDING = 'PENDING', _('بانتظار الموافقة')
        ACTIVE = 'ACTIVE', _('نشط ومفعل')
        SUSPENDED = 'SUSPENDED', _('موقوف مؤقتاً')
        REJECTED = 'REJECTED', _('مرفوض')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_('البريد الإلكتروني'), unique=True, db_index=True)
    full_name = models.CharField(_('الاسم الكامل'), max_length=255)
    phone = models.CharField(_('رقم الهاتف'), max_length=20, blank=True, null=True)
    
    role = models.CharField(
        _('الدور في النظام'),
        max_length=20,
        choices=Role.choices,
        default=Role.EMPLOYEE,
        db_index=True
    )
    
    account_status = models.CharField(
        _('حالة الحساب'),
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING,
        db_index=True
    )

    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_users',
        verbose_name=_('أنشئ بواسطة')
    )

    is_active = models.BooleanField(_('حساب مفعل'), default=True)
    is_staff = models.BooleanField(_('دخول لوحة الإدارة'), default=False)

    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ آخر تحديث'), auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        verbose_name = _('مستخدم')
        verbose_name_plural = _('المستخدمون')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name} ({self.email}) - [{self.get_role_display()}]"

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN or self.is_superuser

    @property
    def is_admin(self):
        return self.role in [self.Role.SUPER_ADMIN, self.Role.ADMIN]

    @property
    def is_deputy(self):
        return self.role == self.Role.DEPUTY_ADMIN

    @property
    def is_employee(self):
        return self.role == self.Role.EMPLOYEE

    @property
    def organization(self):
        """المنشأة المرتبطة بالمستخدم سواء كان مديراً، نائباً، أو موظفاً."""
        if hasattr(self, 'managed_organization'):
            return self.managed_organization
        if hasattr(self, 'employee_profile') and self.employee_profile.organization:
            return self.employee_profile.organization
        if self.role == self.Role.DEPUTY_ADMIN and self.created_by and hasattr(self.created_by, 'managed_organization'):
            return self.created_by.managed_organization
        return None
