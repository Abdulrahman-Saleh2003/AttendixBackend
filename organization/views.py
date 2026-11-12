from rest_framework import viewsets, permissions, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction

from accounts.models import User
from accounts.permissions import IsAdminUser, IsSuperAdminUser
from .models import Organization, Department, Worksite, Shift
from .serializers import (
    OrganizationSerializer,
    OrganizationPublicListSerializer,
    DepartmentSerializer,
    WorksiteSerializer,
    ShiftSerializer
)


class AvailableOrganizationsView(generics.ListAPIView):
    """
    استعراض جميع المنشآت النشطة وأكوادها (مخصص لواجهة الموظف لاختيار المنشأة المناسبة).
    متاح للجميع حتى قبل إنشاء الحساب لاختيار المنشأة أثناء التسجيل.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = OrganizationPublicListSerializer
    pagination_class = None

    def get_queryset(self):
        return Organization.objects.filter(is_active=True).select_related('admin').order_by('name')


class OrganizationViewSet(viewsets.ModelViewSet):
    """
    إدارة المنشآت:
    - السوبر أدمن: يمكنه عرض، تعديل، حذف، وإيقاف/تفعيل أي منشأة.
    - الأدمن: يرى منشأته الخاصة فقط.
    """
    serializer_class = OrganizationSerializer

    def get_permissions(self):
        if self.action in ['destroy', 'toggle_status']:
            return [IsSuperAdminUser()]
        return [IsAdminUser()]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return Organization.objects.all().select_related('admin')
        return Organization.objects.filter(admin=user)

    @action(detail=True, methods=['post'], url_path='toggle-status')
    def toggle_status(self, request, pk=None):
        """
        خاص بالسوبر أدمن:
        إيقاف منشأة مؤقتاً (مثلاً لانتهاء الاشتراك بانتظار الدفع اليدوي) أو إعادة تفعيلها.
        """
        org = self.get_object()
        new_status = request.data.get('is_active')

        if new_status is None:
            # عكس الحالة إذا لم تُرسل
            new_status = not org.is_active
        else:
            new_status = bool(new_status)

        org.is_active = new_status
        org.save()

        msg = f"تم تفعيل نشاط المنشأة ({org.name}) بنجاح." if new_status else f"تم إيقاف نشاط المنشأة ({org.name}) مؤقتاً بسبب الاشتراك."
        return Response({
            "detail": msg,
            "organization_id": str(org.id),
            "organization_name": org.name,
            "is_active": org.is_active
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """
        خاص بالسوبر أدمن:
        حذف المنشأة وحذف كل ما يتعلق بها جذرياً (الأدمن، الموظفين، الحضور، الأجهزة، المواقع).
        """
        org = self.get_object()
        org_name = org.name

        with transaction.atomic():
            admin_user = org.admin
            # جمع مستخدمي الموظفين التابعين للمنشأة لحذفهم
            employee_users = list(User.objects.filter(employee_profile__organization=org))
            # جمع نواب المدير التابعين لهذا الأدمن
            deputy_users = list(User.objects.filter(role=User.Role.DEPUTY_ADMIN, created_by=admin_user))

            # حذف المنشأة (يتولى كاسكيد الأقسام والورديات والمواقع والموظفين والحضور)
            org.delete()

            # حذف حسابات المستخدمين للموظفين والنواب والمدير نفسه
            for emp_user in employee_users:
                emp_user.delete()
            for dep_user in deputy_users:
                dep_user.delete()
            if admin_user:
                admin_user.delete()

        return Response({
            "detail": f"تم حذف المنشأة ({org_name}) وجميع حسابات الإدارة والموظفين وسجلات الحضور التابعة لها بنجاح."
        }, status=status.HTTP_200_OK)


class DepartmentViewSet(viewsets.ModelViewSet):
    """إدارة الأقسام (عرض، إضافة، تعديل، حذف)."""
    serializer_class = DepartmentSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAdminUser()]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return Department.objects.all()
        org = user.organization
        if org:
            return Department.objects.filter(organization=org)
        return Department.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        org = user.organization
        serializer.save(organization=org)


class WorksiteViewSet(viewsets.ModelViewSet):
    """إدارة مواقع العمل المعتمدة ونطاقات الـ GPS."""
    serializer_class = WorksiteSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAdminUser()]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return Worksite.objects.all()
        org = user.organization
        if org:
            return Worksite.objects.filter(organization=org)
        return Worksite.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        org = user.organization
        serializer.save(organization=org)


class ShiftViewSet(viewsets.ModelViewSet):
    """إدارة الورديات ومواعيد العمل وفترات السماح."""
    serializer_class = ShiftSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'current']:
            return [permissions.IsAuthenticated()]
        return [IsAdminUser()]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return Shift.objects.all()
        org = user.organization
        if org:
            return Shift.objects.filter(organization=org)
        return Shift.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        org = user.organization
        serializer.save(organization=org)

    @action(detail=False, methods=['get', 'post', 'put', 'patch'], url_path='current')
    def current(self, request):
        """
        جلب أو تحديث الدوام الموحد للمنشأة (الافتراضي من 08:00 صباحاً إلى 04:00 مساءً).
        """
        user = request.user
        org = user.organization
        if not org:
            return Response(
                {"detail": "لا توجد منشأة مرتبطة بحسابك."},
                status=status.HTTP_400_BAD_REQUEST
            )

        shift = Shift.objects.filter(organization=org, is_active=True).first()
        if not shift:
            from datetime import time
            shift = Shift.objects.create(
                organization=org,
                name="الدوام الرسمي الموحد",
                start_time=time(8, 0),
                end_time=time(16, 0),
                grace_minutes=20,
                working_days="Sun,Mon,Tue,Wed,Thu",
                is_active=True
            )

        if request.method in ['POST', 'PUT', 'PATCH']:
            if not (user.is_admin or user.is_super_admin):
                return Response(
                    {"detail": "فقط مدير المنشأة مصرح له بتعديل مواعيد الدوام."},
                    status=status.HTTP_403_FORBIDDEN
                )
            serializer = ShiftSerializer(shift, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response({
                "detail": "تم تحديث مواعيد الدوام الرسمي للمنشأة بنجاح ✅",
                "shift": serializer.data
            }, status=status.HTTP_200_OK)

        serializer = ShiftSerializer(shift)
        return Response(serializer.data, status=status.HTTP_200_OK)
