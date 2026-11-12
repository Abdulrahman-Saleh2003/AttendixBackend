from django.utils import timezone
from django.db import transaction
from rest_framework import generics, status, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsAdminUser, IsDeputyOrAdmin
from .models import Employee, RegisteredDevice, EmployeeShiftAssignment, OrganizationJoinRequest
from .serializers import (
    EmployeeRegistrationSerializer,
    EmployeeDetailSerializer,
    EmployeeStatusUpdateSerializer,
    DeviceRegistrationRequestSerializer,
    RegisteredDeviceSerializer,
    DeviceStatusUpdateSerializer,
    ShiftAssignmentSerializer,
    OrganizationJoinRequestSerializer,
    CreateJoinRequestSerializer,
    DecideJoinRequestSerializer,
    AdminEmployeeCreateSerializer
)


class EmployeeRegisterView(generics.CreateAPIView):
    """
    تسجيل حساب موظف جديد من تطبيق الجوال.
    متاح للجميع بدون مصادقة مسبقة.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = EmployeeRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        return Response({
            "detail": "تم إنشاء حسابك بنجاح. يمكنك الآن تسجيل الدخول واختيار المنشأة لإرسال طلب الانضمام.",
            "employee_id": str(employee.id),
            "employee_code": employee.employee_code,
            "status": employee.user.account_status
        }, status=status.HTTP_201_CREATED)


class EmployeeJoinRequestView(APIView):
    """
    إدارة ومتابعة طلب انضمام الموظف للمنشأة:
    - GET: استعراض حالة طلب الانضمام الحالي وسجل الطلبات السابقة للموظف.
    - POST: إرسال طلب انضمام إلى منشأة محددة عبر كود المنشأة.
            [ممنوع إرسال طلب جديد إذا كان هناك طلب معلق قيد المراجعة إلا إذا تم الرفض].
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'employee_profile'):
            return Response({"detail": "المستخدم الحالي ليس موظفاً."}, status=status.HTTP_403_FORBIDDEN)

        employee = request.user.employee_profile
        requests = OrganizationJoinRequest.objects.filter(employee=employee).order_by('-requested_at')
        pending_request = requests.filter(status=OrganizationJoinRequest.RequestStatus.PENDING).first()
        is_joined = employee.organization is not None

        return Response({
            "is_joined": is_joined,
            "current_organization": {
                "id": str(employee.organization.id),
                "name": employee.organization.name,
                "code": employee.organization.code
            } if is_joined else None,
            "has_pending_request": pending_request is not None,
            "pending_request": OrganizationJoinRequestSerializer(pending_request).data if pending_request else None,
            "all_requests": OrganizationJoinRequestSerializer(requests, many=True).data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        if not hasattr(request.user, 'employee_profile'):
            return Response({"detail": "المستخدم الحالي ليس موظفاً."}, status=status.HTTP_403_FORBIDDEN)

        serializer = CreateJoinRequestSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        join_req = serializer.save()

        return Response({
            "detail": f"تم إرسال طلب الانضمام إلى منشأة '{join_req.organization.name}' بنجاح، بانتظار موافقة الأدمن.",
            "request": OrganizationJoinRequestSerializer(join_req).data
        }, status=status.HTTP_201_CREATED)


class AdminJoinRequestsListView(generics.ListAPIView):
    """
    استعراض طلبات الانضمام الواردة لمنشأة الأدمن فقط:
    - الأدمن يرى فقط طلبات الانضمام الخاصة بمنشأته.
    - إمكانية الفلترة بحسب الحالة: ?status=PENDING
    """
    permission_classes = [IsAdminUser]
    serializer_class = OrganizationJoinRequestSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            queryset = OrganizationJoinRequest.objects.all()
        elif hasattr(user, 'managed_organization'):
            queryset = OrganizationJoinRequest.objects.filter(organization=user.managed_organization)
        else:
            queryset = OrganizationJoinRequest.objects.none()

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset.select_related('employee__user', 'organization').order_by('-requested_at')


class AdminJoinRequestDecisionView(APIView):
    """
    قرار الأدمن بقبول أو رفض طلب انضمام الموظف لمنشأته:
    - في حال القبول (APPROVE): يتم تفعيل حساب الموظف وربطه رسمياً بالمنشأة.
    - في حال الرفض (REJECT): يتم تسجيل الرفض مع الملاحظات، ويتاح للموظف فوراً إرسال طلب لمنشأة أخرى.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            join_req = OrganizationJoinRequest.objects.select_related('employee__user', 'organization').get(pk=pk)
        except OrganizationJoinRequest.DoesNotExist:
            return Response({"detail": "طلب الانضمام غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        # التحقق من أن الأدمن يملك صلاحية على هذه المنشأة
        if not request.user.is_super_admin:
            if not hasattr(request.user, 'managed_organization') or join_req.organization != request.user.managed_organization:
                return Response({"detail": "ليس لديك صلاحية اتخاذ قرار على طلب يخص منشأة أخرى."}, status=status.HTTP_403_FORBIDDEN)

        if join_req.status != OrganizationJoinRequest.RequestStatus.PENDING:
            return Response({
                "detail": f"تم اتخاذ قرار مسبق على هذا الطلب بالفعل ({join_req.get_status_display()})."
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = DecideJoinRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data['action']
        comment = serializer.validated_data.get('comment', '')

        with transaction.atomic():
            join_req.decided_by = request.user
            join_req.decided_at = timezone.now()
            join_req.admin_comment = comment

            employee = join_req.employee
            user = employee.user

            if action == 'APPROVE':
                join_req.status = OrganizationJoinRequest.RequestStatus.APPROVED
                join_req.save()

                # تعيين أو توليد الرقم الوظيفي الرسمي المعتمد للموظف داخل المنشأة تلقائياً
                assigned_code = serializer.validated_data.get('assigned_employee_code', '').strip()
                if assigned_code:
                    if Employee.objects.filter(employee_code=assigned_code).exclude(pk=employee.pk).exists():
                        return Response({
                            "detail": f"الرقم الوظيفي ({assigned_code}) مستخدم مسبقاً لموظف آخر."
                        }, status=status.HTTP_400_BAD_REQUEST)
                    employee.employee_code = assigned_code
                elif not employee.employee_code or employee.employee_code.startswith(('PENDING-', 'TMP-')):
                    existing_count = Employee.objects.filter(
                        organization=join_req.organization
                    ).exclude(employee_code__startswith='PENDING-').count()
                    next_num = 101 + existing_count
                    generated_code = f"EMP-{next_num}"
                    while Employee.objects.filter(employee_code=generated_code).exclude(pk=employee.pk).exists():
                        next_num += 1
                        generated_code = f"EMP-{next_num}"
                    employee.employee_code = generated_code

                # ربط الموظف بالمنشأة وتفعيل حسابه
                employee.organization = join_req.organization
                employee.save()

                user.account_status = User.AccountStatus.ACTIVE
                user.is_active = True
                user.created_by = request.user
                user.save()

                return Response({
                    "detail": f"تمت الموافقة على انضمام الموظف ({user.full_name}) وتوليد الرقم الوظيفي ({employee.employee_code}) وتفعيل حسابه بنجاح.",
                    "employee_code": employee.employee_code,
                    "organization_name": join_req.organization.name
                }, status=status.HTTP_200_OK)

            else:  # REJECT
                join_req.status = OrganizationJoinRequest.RequestStatus.REJECTED
                join_req.save()

                return Response({
                    "detail": f"تم رفض طلب انضمام الموظف ({user.full_name}). أصبح بإمكان الموظف الآن إرسال طلب لمنشأة أخرى."
                }, status=status.HTTP_200_OK)


class AdminEmployeeListView(generics.ListAPIView):
    """
    استعراض قائمة الموظفين:
    - الأدمن يرى فقط موظفي منشأته التابعين له!
    - السوبر أدمن يرى موظفي جميع المنشآت.
    """
    permission_classes = [IsDeputyOrAdmin]
    serializer_class = EmployeeDetailSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Employee.objects.select_related('user', 'department', 'assigned_worksite', 'organization').prefetch_related('devices').all()

        # عزل البيانات لكل منشأة
        if not user.is_super_admin:
            org = user.organization
            if org:
                queryset = queryset.filter(organization=org)
            else:
                queryset = queryset.none()

        status_param = self.request.query_params.get('status')
        dept_param = self.request.query_params.get('department')
        if status_param:
            queryset = queryset.filter(user__account_status=status_param)
        if dept_param:
            queryset = queryset.filter(department_id=dept_param)

        return queryset.order_by('employee_code')


class AdminEmployeeAddView(APIView):
    """
    مخصص للأدمن:
    إضافة موظف جديد مباشرة لمنشأته وتوليد رقمه الوظيفي دون الحاجة لطلب انضمام.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = AdminEmployeeCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        return Response({
            "detail": f"تمت إضافة الموظف ({employee.full_name}) وتوليد الرقم الوظيفي ({employee.employee_code}) بنجاح.",
            "employee": EmployeeDetailSerializer(employee).data
        }, status=status.HTTP_201_CREATED)


class AdminEmployeeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """جلب، تعديل، وحذف بيانات موظف معين من قبل الإدارة."""
    permission_classes = [IsAdminUser]
    serializer_class = EmployeeDetailSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return Employee.objects.all()
        org = user.organization
        if org:
            return Employee.objects.filter(organization=org)
        return Employee.objects.none()

    def perform_destroy(self, instance):
        with transaction.atomic():
            user = instance.user
            instance.delete()
            if user:
                user.delete()


class AdminEmployeeDeleteView(APIView):
    """
    مخصص للأدمن:
    حذف موظف ومسح بياناته وحسابه وأجهزته التابعة له.
    """
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        user = request.user
        queryset = Employee.objects.all() if user.is_super_admin else Employee.objects.filter(organization=user.organization)
        try:
            employee = queryset.get(pk=pk)
        except Employee.DoesNotExist:
            return Response({"detail": "الموظف غير موجود أو ليس لديك صلاحية لحذفه."}, status=status.HTTP_404_NOT_FOUND)

        emp_name = employee.full_name
        with transaction.atomic():
            emp_user = employee.user
            employee.delete()
            if emp_user:
                emp_user.delete()

        return Response({"detail": f"تم حذف الموظف ({emp_name}) وحسابه بنجاح."}, status=status.HTTP_200_OK)


class AdminEmployeeStatusUpdateView(APIView):
    """تغيير حالة حساب الموظف (قبول / رفض / إيقاف مؤقت)."""
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            employee = Employee.objects.get(pk=pk)
        except Employee.DoesNotExist:
            return Response({"detail": "الموظف غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_super_admin and hasattr(request.user, 'managed_organization'):
            if employee.organization != request.user.managed_organization:
                return Response({"detail": "الموظف يتبع لمنشأة أخرى."}, status=status.HTTP_403_FORBIDDEN)

        serializer = EmployeeStatusUpdateSerializer(data=request.data)
        if serializer.is_valid():
            new_status = serializer.validated_data['account_status']
            employee.user.account_status = new_status
            if new_status == User.AccountStatus.ACTIVE:
                employee.user.is_active = True
            elif new_status in [User.AccountStatus.SUSPENDED, User.AccountStatus.REJECTED]:
                employee.user.is_active = False

            if 'notes' in serializer.validated_data:
                employee.notes = serializer.validated_data['notes']

            employee.user.save()
            employee.save()
            return Response({
                "detail": f"تم تحديث حالة الموظف بنجاح إلى: {employee.user.get_account_status_display()}"
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeviceRegisterView(APIView):
    """
    تسجيل جهاز الهاتف من تطبيق الموظف.
    يرسل التطبيق installation_id والمفتاح العام.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not hasattr(request.user, 'employee_profile'):
            return Response({"detail": "المستخدم الحالي ليس موظفاً."}, status=status.HTTP_403_FORBIDDEN)

        employee = request.user.employee_profile
        serializer = DeviceRegistrationRequestSerializer(data=request.data)
        if serializer.is_valid():
            device = serializer.save(employee=employee, status=RegisteredDevice.DeviceStatus.PENDING)
            return Response({
                "detail": "تم تسجيل الهاتف بنجاح، بانتظار اعتماد المدير للجهاز.",
                "device_id": str(device.id),
                "status": device.status
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminDeviceListView(generics.ListAPIView):
    """
    قائمة أجهزة موظفي المنشأة للمدير.
    GET /api/employees/admin/devices/
    فلترة: ?status=PENDING | ACTIVE | REJECTED | REVOKED
    """
    permission_classes = [IsAdminUser]
    serializer_class = RegisteredDeviceSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = RegisteredDevice.objects.select_related(
            'employee__user', 'employee__organization'
        )
        if not user.is_super_admin:
            org = user.organization
            queryset = queryset.filter(employee__organization=org) if org else queryset.none()

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset.order_by('-created_at')


class AdminDeviceStatusUpdateView(APIView):
    """اعتماد أو رفض أو إلغاء جهاز هاتف من قبل المدير."""
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            device = RegisteredDevice.objects.select_related('employee').get(pk=pk)
        except RegisteredDevice.DoesNotExist:
            return Response({"detail": "الجهاز غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_super_admin and hasattr(request.user, 'managed_organization'):
            if device.employee.organization != request.user.managed_organization:
                return Response({"detail": "الجهاز يتبع لموظف في منشأة أخرى."}, status=status.HTTP_403_FORBIDDEN)

        serializer = DeviceStatusUpdateSerializer(data=request.data)
        if serializer.is_valid():
            new_status = serializer.validated_data['status']
            device.status = new_status
            if new_status == RegisteredDevice.DeviceStatus.ACTIVE:
                device.approved_at = timezone.now()
                device.approved_by = request.user
            elif new_status == RegisteredDevice.DeviceStatus.REVOKED:
                device.revoked_at = timezone.now()

            device.save()
            return Response({
                "detail": f"تم تحديث حالة الجهاز إلى: {device.get_status_display()}"
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminDeviceApproveView(APIView):
    """
    اعتماد جهاز الموظف مباشرة عبر:
    POST /api/employees/admin/devices/<pk>/approve/
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            device = RegisteredDevice.objects.select_related('employee__organization').get(pk=pk)
        except RegisteredDevice.DoesNotExist:
            return Response({"detail": "الجهاز غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_super_admin:
            org = request.user.organization
            if not org or device.employee.organization != org:
                return Response({"detail": "الجهاز يتبع لموظف في منشأة أخرى."}, status=status.HTTP_403_FORBIDDEN)

        device.status = RegisteredDevice.DeviceStatus.ACTIVE
        device.approved_at = timezone.now()
        device.approved_by = request.user
        device.save()
        return Response({
            "detail": f"تم اعتماد الجهاز ({device.manufacturer} {device.model}) بنجاح ✅"
        }, status=status.HTTP_200_OK)


class AdminDeviceRejectView(APIView):
    """
    رفض جهاز الموظف عبر:
    POST /api/employees/admin/devices/<pk>/reject/
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            device = RegisteredDevice.objects.select_related('employee__organization').get(pk=pk)
        except RegisteredDevice.DoesNotExist:
            return Response({"detail": "الجهاز غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_super_admin:
            org = request.user.organization
            if not org or device.employee.organization != org:
                return Response({"detail": "الجهاز يتبع لموظف في منشأة أخرى."}, status=status.HTTP_403_FORBIDDEN)

        device.status = RegisteredDevice.DeviceStatus.REJECTED
        device.save()
        return Response({
            "detail": f"تم رفض الجهاز ({device.manufacturer} {device.model})."
        }, status=status.HTTP_200_OK)


class AdminDeviceResetView(APIView):
    """
    إلغاء ربط جهاز موظف معين وتصفيره:
    POST /api/employees/admin/<employee_pk>/reset-device/
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            employee = Employee.objects.select_related('organization').get(pk=pk)
        except Employee.DoesNotExist:
            return Response({"detail": "الموظف غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_super_admin:
            org = request.user.organization
            if not org or employee.organization != org:
                return Response({"detail": "الموظف ينتمي لمنشأة أخرى."}, status=status.HTTP_403_FORBIDDEN)

        # إلغاء جميع أجهزته النشطة
        updated = employee.devices.filter(
            status=RegisteredDevice.DeviceStatus.ACTIVE
        ).update(
            status=RegisteredDevice.DeviceStatus.REVOKED,
            revoked_at=timezone.now()
        )
        return Response({
            "detail": f"تم تصفير وإلغاء ربط {updated} جهاز للموظف ({employee.full_name}) بنجاح ✅"
        }, status=status.HTTP_200_OK)


class ShiftAssignmentViewSet(viewsets.ModelViewSet):
    """تعيين الورديات للموظفين."""
    permission_classes = [IsAdminUser]
    serializer_class = ShiftAssignmentSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return EmployeeShiftAssignment.objects.all()
        if hasattr(user, 'managed_organization'):
            return EmployeeShiftAssignment.objects.filter(employee__organization=user.managed_organization)
        return EmployeeShiftAssignment.objects.none()
