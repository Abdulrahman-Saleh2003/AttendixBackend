import random
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from .models import User


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """مخصص لتسجيل الدخول وإرجاع بيانات المستخدم الإضافية مع التوكن."""
    username_field = 'email'
    installation_id = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, attrs):
        email = attrs.get('email', '')
        password = attrs.get('password', '')
        installation_id = attrs.get('installation_id', None)

        # التحقق الدقيق من حالة الحساب ورسائل التنبيه قبل اكتمال المصادقة
        user = User.objects.filter(email__iexact=email).first()
        if user and user.check_password(password):
            # 1. حساب المدير بانتظار موافقة السوبر أدمن
            if user.role == User.Role.ADMIN and user.account_status == User.AccountStatus.PENDING:
                raise serializers.ValidationError({
                    "account_status": "حسابك كمدير قيد المراجعة والاعتماد من قبل إدارة النظام (السوبر أدمن)."
                })

            # 2. الحسابات الموقوفة أو المرفوضة
            if user.account_status == User.AccountStatus.SUSPENDED:
                raise serializers.ValidationError({
                    "account_status": "تم إيقاف حسابك مؤقتاً، يرجى التواصل مع الإدارة."
                })

            if user.account_status == User.AccountStatus.REJECTED:
                raise serializers.ValidationError({
                    "account_status": "تم رفض طلب تسجيل الحساب من قبل الإدارة."
                })

            # 3. التحقق من اشتراك ونشاط المنشأة
            org = user.organization
            if org and not org.is_active and not user.is_super_admin:
                raise serializers.ValidationError({
                    "organization": "تم إيقاف نشاط المنشأة مؤقتاً (يرجى مراجعة إدارة المنصة لتجديد الاشتراك)."
                })

        data = super().validate(attrs)

        # 4. التحقق من قفل الجهاز للموظفين ونواب المدراء
        device_locked = False
        if self.user.role in (User.Role.EMPLOYEE, User.Role.DEPUTY_ADMIN):
            employee_profile = getattr(self.user, 'employee_profile', None)
            if employee_profile is not None:
                active_device = employee_profile.active_device
                if active_device is not None:
                    device_locked = True
                    if installation_id and installation_id != active_device.installation_id:
                        raise serializers.ValidationError({
                            "detail": (
                                f"⚠️ تم رصد محاولة دخول من جهاز غير معتمد. "
                                f"يمكنك تسجيل الدخول فقط من جهازك المسجل "
                                f"({active_device.manufacturer} {active_device.model}). "
                                f"إذا فقدت هاتفك، تواصل مع مدير المنشأة لإعادة تعيين الجهاز."
                            )
                        })

        org_data = None
        if user and user.organization:
            org = user.organization
            org_data = {
                'id': str(org.id),
                'name': org.name,
                'code': org.code,
                'is_active': org.is_active
            }

        data['device_locked'] = device_locked
        data['user'] = {
            'id': str(self.user.id),
            'email': self.user.email,
            'full_name': self.user.full_name,
            'role': self.user.role,
            'account_status': self.user.account_status,
            'is_super_admin': self.user.is_super_admin,
            'is_admin': self.user.is_admin,
            'is_deputy': self.user.is_deputy,
            'is_employee': self.user.is_employee,
            'organization': org_data
        }
        return data


class UserSerializer(serializers.ModelSerializer):
    """سيريالايزر عرض بيانات المستخدم الأساسية."""
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    account_status_display = serializers.CharField(source='get_account_status_display', read_only=True)
    organization_name = serializers.SerializerMethodField()
    organization_code = serializers.SerializerMethodField()
    organization_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'phone', 'role', 'role_display',
            'account_status', 'account_status_display', 'organization_id',
            'organization_name', 'organization_code', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_organization_id(self, obj):
        org = obj.organization
        return str(org.id) if org else None

    def get_organization_name(self, obj):
        org = obj.organization
        return org.name if org else None

    def get_organization_code(self, obj):
        org = obj.organization
        return org.code if org else None


class AdminCreateSerializer(serializers.ModelSerializer):
    """
    سيريالايزر لتسجيل أو إنشاء مدير جديد (Admin) مع منشأته:
    - في حال التسجيل الذاتي من التطبيق: ينشأ بحالة PENDING وغير نشط وبانتظار موافقة السوبر أدمن.
    - في حال الإنشاء المباشر من السوبر أدمن: ينشأ معتمداً ACTIVE.
    """
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    role = serializers.ChoiceField(
        choices=[(User.Role.ADMIN, 'مدير'), (User.Role.DEPUTY_ADMIN, 'نائب مدير')],
        default=User.Role.ADMIN
    )
    organization_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    organization_code = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'password', 'full_name', 'phone', 'role', 'organization_name', 'organization_code']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("هذا البريد الإلكتروني مسجل مسبقاً.")
        return value.lower()

    def create(self, validated_data):
        from organization.models import Organization

        password = validated_data.pop('password')
        org_name = validated_data.pop('organization_name', None)
        org_code = validated_data.pop('organization_code', None)

        request = self.context.get('request')
        is_by_superadmin = bool(request and request.user and request.user.is_authenticated and request.user.is_super_admin)
        created_by = request.user if is_by_superadmin else None

        initial_status = User.AccountStatus.ACTIVE if is_by_superadmin else User.AccountStatus.PENDING
        initial_active = True if is_by_superadmin else False
        initial_org_active = True if is_by_superadmin else False

        with transaction.atomic():
            user = User.objects.create_user(
                password=password,
                created_by=created_by,
                account_status=initial_status,
                is_active=initial_active,
                is_staff=True,
                **validated_data
            )

            # إنشاء المنشأة التابعة للأدمن
            if not org_name:
                org_name = f"منشأة {user.full_name}"
            if not org_code:
                import re
                letters = re.findall(r'[A-Za-z]', org_name)
                prefix = ''.join(letters[:4]).upper() if len(letters) >= 3 else "ORG"
                org_code = f"{prefix}-{random.randint(1000, 9999)}"
                while Organization.objects.filter(code=org_code).exists():
                    org_code = f"{prefix}-{random.randint(1000, 9999)}"

            Organization.objects.create(
                admin=user,
                name=org_name,
                code=org_code,
                is_active=initial_org_active
            )

        return user


class AdminUpdateSerializer(serializers.ModelSerializer):
    """سيريالايزر لتعديل بيانات الأدمن من قبل السوبر أدمن."""
    class Meta:
        model = User
        fields = ['full_name', 'phone', 'role', 'account_status', 'is_active']

    def validate_role(self, value):
        if value not in [User.Role.ADMIN, User.Role.DEPUTY_ADMIN]:
            raise serializers.ValidationError("يمكن تغيير الدور إلى مدير أو نائب مدير فقط.")
        return value


class SuperAdminDecisionSerializer(serializers.Serializer):
    """سيريالايزر لقرار السوبر أدمن بقبول أو رفض تسجيل المدير."""
    action = serializers.ChoiceField(choices=['APPROVE', 'REJECT'])
    notes = serializers.CharField(required=False, allow_blank=True)


class DeputyAdminCreateSerializer(serializers.ModelSerializer):
    """سيريالايزر خاص بالمدير (Admin) لإنشاء نائب مدير (Deputy Admin) لمنشأته."""
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ['id', 'email', 'password', 'full_name', 'phone']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("هذا البريد الإلكتروني مسجل مسبقاً.")
        return value.lower()

    def create(self, validated_data):
        password = validated_data.pop('password')
        request = self.context.get('request')
        created_by = request.user

        user = User.objects.create_user(
            password=password,
            created_by=created_by,
            role=User.Role.DEPUTY_ADMIN,
            account_status=User.AccountStatus.ACTIVE,
            is_active=True,
            is_staff=True,
            **validated_data
        )
        return user


class ChangePasswordSerializer(serializers.Serializer):
    """سيريالايزر لتغيير كلمة المرور للمستخدم الحالي."""
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("كلمة المرور الحالية غير صحيحة.")
        return value
