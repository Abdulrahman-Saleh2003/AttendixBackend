from rest_framework.permissions import BasePermission
from .models import User


class IsSuperAdminUser(BasePermission):
    """
    صلاحية حصرية للسوبر أدمن (مالك النظام).
    هو الوحيد المخول بإنشاء وإدارة حسابات المدراء (Admins).
    """
    message = "هذا الإجراء مخصص حصرياً للسوبر أدمن (مالك النظام)."

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_super_admin
        )


class IsAdminUser(BasePermission):
    """صلاحية للمدراء والسوبر أدمن معاً."""
    message = "يتطلب هذا الإجراء صلاحيات مدير أو سوبر أدمن."

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_admin
        )


class IsDeputyOrAdmin(BasePermission):
    """صلاحية للمدراء، نواب المدراء، أو السوبر أدمن."""
    message = "يتطلب هذا الإجراء صلاحيات إدارة أو نائب مدير."

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_admin or request.user.is_deputy)
        )


class IsEmployeeUser(BasePermission):
    """صلاحية خاصة بالموظف النشط والمعتمد."""
    message = "يجب أن تكون موظفاً معتمداً وحسابك نشط للقيام بهذا الإجراء."

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_employee and
            request.user.account_status == User.AccountStatus.ACTIVE
        )
