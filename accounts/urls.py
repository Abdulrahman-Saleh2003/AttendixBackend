from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    CustomTokenObtainPairView,
    AdminRegisterView,
    SuperAdminAdminListCreateView,
    SuperAdminAdminDetailView,
    SuperAdminPendingAdminsView,
    SuperAdminAdminDecisionView,
    AdminDeputyListCreateView,
    AdminDeputyDeleteView,
    UserProfileView,
    ChangePasswordView
)

app_name = 'accounts'

urlpatterns = [
    # المصادقة والتوكنات والتسجيل
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('register-admin/', AdminRegisterView.as_view(), name='register_admin'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # الملف الشخصي وكلمة المرور
    path('profile/', UserProfileView.as_view(), name='user_profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),

    # لوحة السوبر أدمن لإدارة واعتماد المدراء
    path('superadmin/pending-admins/', SuperAdminPendingAdminsView.as_view(), name='superadmin_pending_admins'),
    path('superadmin/admins/<uuid:pk>/decide/', SuperAdminAdminDecisionView.as_view(), name='superadmin_admin_decide'),
    path('superadmin/admins/', SuperAdminAdminListCreateView.as_view(), name='superadmin_admins_list_create'),
    path('superadmin/admins/<uuid:pk>/', SuperAdminAdminDetailView.as_view(), name='superadmin_admin_detail'),

    # لوحة الأدمن لإدارة نواب المدراء (Deputies)
    path('admin/deputies/', AdminDeputyListCreateView.as_view(), name='admin_deputies_list_create'),
    path('admin/deputies/<uuid:pk>/', AdminDeputyDeleteView.as_view(), name='admin_deputy_delete'),
]
