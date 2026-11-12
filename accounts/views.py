from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db import transaction

from .models import User
from .permissions import IsSuperAdminUser, IsAdminUser
from .serializers import (
    CustomTokenObtainPairSerializer,
    UserSerializer,
    AdminCreateSerializer,
    AdminUpdateSerializer,
    SuperAdminDecisionSerializer,
    DeputyAdminCreateSerializer,
    ChangePasswordSerializer
)


class AdminRegisterView(generics.CreateAPIView):
    """
    تسجيل حساب مدير جديد (Admin) مع تأسيس منشأته من التطبيق.
    ينشأ الحساب بحالة PENDING وغير نشط حتى يقبله السوبر أدمن.
    """
    permission_classes = [AllowAny]
    serializer_class = AdminCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        admin_user = serializer.save()
        org = getattr(admin_user, 'managed_organization', None)
        return Response({
            "detail": "تم إرسال طلب تسجيل المدير والمنشأة بنجاح. حسابك الآن قيد مراجعة واعتماد السوبر أدمن قبل تسجيل الدخول.",
            "user_id": str(admin_user.id),
            "email": admin_user.email,
            "role": admin_user.role,
            "account_status": admin_user.account_status,
            "organization_name": org.name if org else None,
            "organization_code": org.code if org else None
        }, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    """تسجيل الدخول وإصدار Access & Refresh Tokens مع بيانات المستخدم."""
    serializer_class = CustomTokenObtainPairSerializer


class SuperAdminPendingAdminsView(generics.ListAPIView):
    """
    مخصص للسوبر أدمن:
    استعراض طلبات تسجيل المدراء المعلقة (PENDING) بانتظار الموافقة والاعتماد.
    """
    permission_classes = [IsSuperAdminUser]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(
            role=User.Role.ADMIN,
            account_status=User.AccountStatus.PENDING
        ).order_by('-created_at')


class SuperAdminAdminDecisionView(APIView):
    """
    مخصص للسوبر أدمن:
    الموافقة (APPROVE) أو الرفض (REJECT) على طلب تسجيل حساب مدير ومنشأته.
    """
    permission_classes = [IsSuperAdminUser]

    def post(self, request, pk):
        try:
            admin_user = User.objects.get(pk=pk, role=User.Role.ADMIN)
        except User.DoesNotExist:
            return Response({"detail": "حساب المدير المطلوب غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SuperAdminDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data['action']
        notes = serializer.validated_data.get('notes', '')

        with transaction.atomic():
            org = getattr(admin_user, 'managed_organization', None)
            if action == 'APPROVE':
                admin_user.account_status = User.AccountStatus.ACTIVE
                admin_user.is_active = True
                admin_user.save()

                if org:
                    org.is_active = True
                    org.save()

                return Response({
                    "detail": f"تمت الموافقة على حساب المدير ({admin_user.full_name}) وتفعيل منشأته ({org.name if org else ''}) بنجاح.",
                    "account_status": admin_user.account_status,
                    "organization_active": org.is_active if org else None
                }, status=status.HTTP_200_OK)
            else:
                admin_user.account_status = User.AccountStatus.REJECTED
                admin_user.is_active = False
                admin_user.save()

                if org:
                    org.is_active = False
                    org.save()

                return Response({
                    "detail": f"تم رفض طلب تسجيل المدير ({admin_user.full_name}).",
                    "account_status": admin_user.account_status,
                    "notes": notes
                }, status=status.HTTP_200_OK)


class SuperAdminAdminListCreateView(generics.ListCreateAPIView):
    """
    مخصص حصرياً للسوبر أدمن:
    - GET: استعراض جميع المدراء ونواب المدراء.
    - POST: إنشاء مدير (Admin) جديد مباشرة مفعلاً.
    """
    permission_classes = [IsSuperAdminUser]

    def get_queryset(self):
        return User.objects.filter(role__in=[User.Role.ADMIN, User.Role.DEPUTY_ADMIN]).order_by('-created_at')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdminCreateSerializer
        return UserSerializer


class SuperAdminAdminDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    مخصص حصرياً للسوبر أدمن:
    - GET: جلب تفاصيل مدير معين.
    - PATCH / PUT: تعديل بيانات المدير.
    - DELETE: حذف حساب المدير ومنشأته وكل ما يتعلق به نهائياً.
    """
    permission_classes = [IsSuperAdminUser]
    lookup_field = 'pk'

    def get_queryset(self):
        return User.objects.filter(role__in=[User.Role.ADMIN, User.Role.DEPUTY_ADMIN])

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return AdminUpdateSerializer
        return UserSerializer

    def perform_destroy(self, instance):
        with transaction.atomic():
            # حذف المنشأة وما يرتبط بها من موظفين وحضور وأجهزة
            if hasattr(instance, 'managed_organization'):
                instance.managed_organization.delete()
            instance.delete()


class AdminDeputyListCreateView(generics.ListCreateAPIView):
    """
    مخصص للمدير (Admin):
    - GET: استعراض نواب المدير التابعين لمنشأته.
    - POST: إضافة نائب مدير جديد للمنشأة.
    """
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return User.objects.filter(role=User.Role.DEPUTY_ADMIN).order_by('-created_at')
        return User.objects.filter(role=User.Role.DEPUTY_ADMIN, created_by=user).order_by('-created_at')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return DeputyAdminCreateSerializer
        return UserSerializer


class AdminDeputyDeleteView(APIView):
    """
    مخصص للمدير (Admin):
    حذف نائب مدير من منشأته.
    """
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        user = request.user
        try:
            deputy = User.objects.get(pk=pk, role=User.Role.DEPUTY_ADMIN)
        except User.DoesNotExist:
            return Response({"detail": "نائب المدير غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        if not user.is_super_admin and deputy.created_by != user:
            return Response({"detail": "ليس لديك صلاحية لحذف هذا المدير."}, status=status.HTTP_403_FORBIDDEN)

        deputy_name = deputy.full_name
        deputy.delete()
        return Response({"detail": f"تم حذف نائب المدير ({deputy_name}) بنجاح."}, status=status.HTTP_200_OK)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """جلب وتعديل بيانات الملف الشخصي للمستخدم الحالي."""
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    """تغيير كلمة المرور للمستخدم المسجل دخوله حالياً."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            request.user.set_password(serializer.validated_data['new_password'])
            request.user.save()
            return Response({"detail": "تم تغيير كلمة المرور بنجاح."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
