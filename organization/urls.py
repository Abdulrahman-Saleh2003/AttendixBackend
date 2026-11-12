from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AvailableOrganizationsView,
    OrganizationViewSet,
    DepartmentViewSet,
    WorksiteViewSet,
    ShiftViewSet
)

app_name = 'organization'

router = DefaultRouter()
router.register(r'manage', OrganizationViewSet, basename='organization-manage')
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'worksites', WorksiteViewSet, basename='worksite')
router.register(r'shifts', ShiftViewSet, basename='shift')

urlpatterns = [
    # مسار خاص بالموظف لجلب جميع المنشآت النشطة وأكوادها لاختيار منشأته
    path('available/', AvailableOrganizationsView.as_view(), name='available_organizations'),
    path('', include(router.urls)),
]
