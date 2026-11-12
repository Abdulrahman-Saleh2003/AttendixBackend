import uuid
from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.password_validation import validate_password
from accounts.models import User
from organization.models import Organization
from organization.serializers import DepartmentSerializer, WorksiteSerializer, OrganizationPublicListSerializer
from .models import Employee, RegisteredDevice, EmployeeShiftAssignment, OrganizationJoinRequest


class EmployeeRegistrationSerializer(serializers.Serializer):
    """
    تسجيل حساب موظف جديد من تطبيق الجوال.
    الرقم الوظيفي اختياري هنا ويتم توليده تلقائياً فور موافقة المنشأة على انضمامه.
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    full_name = serializers.CharField(required=True, max_length=255)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    employee_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    job_title = serializers.CharField(required=False, allow_blank=True, max_length=150)
    organization_code = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("البريد الإلكتروني مسجل مسبقاً.")
        return value.lower()

    def validate_employee_code(self, value):
        if value and value.strip() and Employee.objects.filter(employee_code=value.strip()).exists():
            raise serializers.ValidationError("الرقم الوظيفي مسجل مسبقاً.")
        return value.strip() if value else ""

    def create(self, validated_data):
        org_code = validated_data.pop('organization_code', None)
        emp_code = validated_data.pop('employee_code', None)

        # توليد كود مؤقت ذكي إذا لم يُدخل الموظف رقماً وظيفياً (سيتم تعيين الرقم الرسمي فور اعتماد المنشأة)
        if not emp_code:
            emp_code = f"PENDING-{uuid.uuid4().hex[:6].upper()}"
            while Employee.objects.filter(employee_code=emp_code).exists():
                emp_code = f"PENDING-{uuid.uuid4().hex[:6].upper()}"

        with transaction.atomic():
            user = User.objects.create_user(
                email=validated_data['email'],
                password=validated_data['password'],
                full_name=validated_data['full_name'],
                phone=validated_data.get('phone', ''),
                role=User.Role.EMPLOYEE,
                account_status=User.AccountStatus.PENDING,
                is_active=True
            )

            employee = Employee.objects.create(
                user=user,
                employee_code=emp_code,
                job_title=validated_data.get('job_title', '')
            )

            # إذا أرسل كود المنشأة مباشرة أثناء التسجيل، ننشئ له طلب انضمام تلقائي
            if org_code:
                try:
                    org = Organization.objects.get(code__iexact=org_code.strip(), is_active=True)
                    OrganizationJoinRequest.objects.create(
                        employee=employee,
                        organization=org,
                        status=OrganizationJoinRequest.RequestStatus.PENDING
                    )
                except Organization.DoesNotExist:
                    pass

            return employee


class OrganizationJoinRequestSerializer(serializers.ModelSerializer):
    """عرض بيانات طلب الانضمام للموظف والأدمن."""
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    organization_code = serializers.CharField(source='organization.code', read_only=True)
    admin_name = serializers.CharField(source='organization.admin.full_name', read_only=True)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    employee_code = serializers.CharField(source='employee.employee_code', read_only=True)
    employee_email = serializers.CharField(source='employee.email', read_only=True)
    employee_phone = serializers.CharField(source='employee.phone', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = OrganizationJoinRequest
        fields = [
            'id', 'organization', 'organization_name', 'organization_code', 'admin_name',
            'employee', 'employee_name', 'employee_code', 'employee_email', 'employee_phone',
            'status', 'status_display', 'notes', 'admin_comment', 'requested_at', 'decided_at'
        ]
        read_only_fields = ['id', 'status', 'admin_comment', 'requested_at', 'decided_at']


class CreateJoinRequestSerializer(serializers.Serializer):
    """
    سيريالايزر إنشاء طلب انضمام إلى منشأة/أدمن محدد.
    يطبق القاعدة الصارمة: ممنوع إرسال طلب جديد إذا كان هناك طلب معلق (PENDING)!
    """
    organization_code = serializers.CharField(required=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_organization_code(self, value):
        try:
            org = Organization.objects.get(code__iexact=value.strip(), is_active=True)
        except Organization.DoesNotExist:
            raise serializers.ValidationError("كود المنشأة المدخل غير صحيح أو أن المنشأة غير نشطة.")
        return org

    def validate(self, attrs):
        request = self.context.get('request')
        employee = request.user.employee_profile

        # 1. هل الموظف معتمد ومنضم بالفعل إلى منشأة؟
        if employee.organization is not None:
            raise serializers.ValidationError(
                f"أنت منضم بالفعل إلى منشأة معتمدة: ({employee.organization.name}). لا يمكنك إرسال طلب انضمام آخر."
            )

        # 2. هل لديه أي طلب معلق PENDING حالياً؟
        pending_request = OrganizationJoinRequest.objects.filter(
            employee=employee,
            status=OrganizationJoinRequest.RequestStatus.PENDING
        ).first()

        if pending_request:
            raise serializers.ValidationError(
                f"لديك طلب معلق حالياً قيد المراجعة لدى منشأة '{pending_request.organization.name}' (كود: {pending_request.organization.code}). "
                "لا يمكنك إرسال طلب جديد إلى أي منشأة إلا إذا رفض الأدمن طلبك الحالي."
            )

        return attrs

    def create(self, validated_data):
        employee = self.context['request'].user.employee_profile
        organization = validated_data['organization_code']
        notes = validated_data.get('notes', '')

        return OrganizationJoinRequest.objects.create(
            employee=employee,
            organization=organization,
            notes=notes,
            status=OrganizationJoinRequest.RequestStatus.PENDING
        )


class DecideJoinRequestSerializer(serializers.Serializer):
    """قرار الأدمن على طلب الانضمام (موافقة أو رفض)."""
    action = serializers.ChoiceField(choices=['APPROVE', 'REJECT'])
    comment = serializers.CharField(required=False, allow_blank=True)
    assigned_employee_code = serializers.CharField(required=False, allow_blank=True)


class RegisteredDeviceSerializer(serializers.ModelSerializer):
    """عرض وتسجيل بيانات أجهزة الهواتف المعتمدة."""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    employee_code = serializers.CharField(source='employee.employee_code', read_only=True)
    employee_email = serializers.CharField(source='employee.email', read_only=True)

    class Meta:
        model = RegisteredDevice
        fields = [
            'id', 'employee', 'employee_name', 'employee_code', 'employee_email',
            'installation_id', 'public_key',
            'manufacturer', 'model', 'os_version', 'status',
            'status_display', 'approved_at', 'created_at'
        ]
        read_only_fields = ['id', 'status', 'approved_at', 'created_at']


class DeviceRegistrationRequestSerializer(serializers.ModelSerializer):
    """طلب تسجيل جهاز جديد من تطبيق الموبايل."""
    class Meta:
        model = RegisteredDevice
        fields = ['installation_id', 'public_key', 'manufacturer', 'model', 'os_version']

    def validate_installation_id(self, value):
        if RegisteredDevice.objects.filter(installation_id=value).exists():
            raise serializers.ValidationError("هذا الجهاز مسجل مسبقاً في النظام.")
        return value


class EmployeeDetailSerializer(serializers.ModelSerializer):
    """تفاصيل الموظف الكاملة مع بيانات المنشأة التابع لها."""
    email = serializers.EmailField(source='user.email', read_only=True)
    full_name = serializers.CharField(source='user.full_name', read_only=True)
    phone = serializers.CharField(source='user.phone', read_only=True)
    account_status = serializers.CharField(source='user.account_status', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    organization_code = serializers.CharField(source='organization.code', read_only=True)
    department = DepartmentSerializer(read_only=True)
    assigned_worksite = WorksiteSerializer(read_only=True)
    devices = RegisteredDeviceSerializer(many=True, read_only=True)

    class Meta:
        model = Employee
        fields = [
            'id', 'email', 'full_name', 'phone', 'employee_code', 'job_title',
            'organization', 'organization_name', 'organization_code',
            'department', 'assigned_worksite', 'account_status', 'is_active',
            'hire_date', 'notes', 'devices', 'created_at'
        ]


class EmployeeStatusUpdateSerializer(serializers.Serializer):
    """تحديث حالة الموظف من قبل المدير (قبول / رفض / إيقاف)."""
    account_status = serializers.ChoiceField(choices=User.AccountStatus.choices)
    notes = serializers.CharField(required=False, allow_blank=True)


class DeviceStatusUpdateSerializer(serializers.Serializer):
    """اعتماد أو رفض أو إلغاء جهاز موظف من قبل المدير."""
    status = serializers.ChoiceField(choices=RegisteredDevice.DeviceStatus.choices)


class ShiftAssignmentSerializer(serializers.ModelSerializer):
    shift_name = serializers.CharField(source='shift.name', read_only=True)

    class Meta:
        model = EmployeeShiftAssignment
        fields = ['id', 'employee', 'shift', 'shift_name', 'valid_from', 'valid_to']


class AdminEmployeeCreateSerializer(serializers.Serializer):
    """سيريالايزر لإضافة موظف مباشرة من قبل المدير لمنشأته."""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    full_name = serializers.CharField(required=True, max_length=255)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    employee_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    job_title = serializers.CharField(required=False, allow_blank=True, max_length=150)
    department_id = serializers.UUIDField(required=False, allow_null=True)
    worksite_id = serializers.UUIDField(required=False, allow_null=True)
    hire_date = serializers.DateField(required=False, allow_null=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("البريد الإلكتروني مسجل مسبقاً.")
        return value.lower()

    def validate_employee_code(self, value):
        if value and value.strip() and Employee.objects.filter(employee_code=value.strip()).exists():
            raise serializers.ValidationError("الرقم الوظيفي مسجل مسبقاً لموظف آخر.")
        return value.strip() if value else ""

    def create(self, validated_data):
        from organization.models import Department, Worksite
        request = self.context.get('request')
        admin = request.user
        org = admin.organization

        if not org:
            raise serializers.ValidationError("المستخدم الحالي ليس مرتبطاً بمنشأة.")

        emp_code = validated_data.get('employee_code')
        if not emp_code:
            existing_count = Employee.objects.filter(organization=org).count()
            next_num = 101 + existing_count
            emp_code = f"EMP-{next_num}"
            while Employee.objects.filter(employee_code=emp_code).exists():
                next_num += 1
                emp_code = f"EMP-{next_num}"

        dept = None
        dept_id = validated_data.get('department_id')
        if dept_id:
            dept = Department.objects.filter(id=dept_id, organization=org).first()

        worksite = None
        worksite_id = validated_data.get('worksite_id')
        if worksite_id:
            worksite = Worksite.objects.filter(id=worksite_id, organization=org).first()

        with transaction.atomic():
            user = User.objects.create_user(
                email=validated_data['email'],
                password=validated_data['password'],
                full_name=validated_data['full_name'],
                phone=validated_data.get('phone', ''),
                role=User.Role.EMPLOYEE,
                account_status=User.AccountStatus.ACTIVE,
                is_active=True,
                created_by=admin
            )

            employee = Employee.objects.create(
                user=user,
                organization=org,
                employee_code=emp_code,
                job_title=validated_data.get('job_title', ''),
                department=dept,
                assigned_worksite=worksite,
                hire_date=validated_data.get('hire_date', timezone.localdate()),
                is_active=True
            )

        return employee
