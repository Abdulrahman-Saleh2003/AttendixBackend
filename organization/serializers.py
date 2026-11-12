from rest_framework import serializers
from .models import Organization, Department, Worksite, Shift


class OrganizationSerializer(serializers.ModelSerializer):
    admin_name = serializers.CharField(source='admin.full_name', read_only=True)
    admin_email = serializers.CharField(source='admin.email', read_only=True)

    class Meta:
        model = Organization
        fields = ['id', 'name', 'code', 'admin', 'admin_name', 'admin_email', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class OrganizationPublicListSerializer(serializers.ModelSerializer):
    """سيريالايزر مبسط يعرض المنشآت النشطة وأكوادها للموظفين الجدد لاختيار المنشأة."""
    admin_name = serializers.CharField(source='admin.full_name', read_only=True)

    class Meta:
        model = Organization
        fields = ['id', 'name', 'code', 'admin_name']


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'organization', 'name', 'code', 'is_active', 'created_at']


class WorksiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Worksite
        fields = ['id', 'organization', 'name', 'address', 'latitude', 'longitude', 'radius_m', 'is_active', 'created_at']


class ShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = ['id', 'organization', 'name', 'start_time', 'end_time', 'grace_minutes', 'working_days', 'is_active', 'created_at']
