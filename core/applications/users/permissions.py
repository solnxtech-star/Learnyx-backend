from rest_framework.permissions import BasePermission

from core.helper.enums import AdminType
from core.helper.enums import UserRole


class CanActivateUsers(BasePermission):
    """
    Restricts activation of users to:
    - School Owner
    - Principal

    Ensures:
    - The acting admin belongs to a school
    - Only privileged admin types can approve/reject
    """

    def has_permission(self, request, view):
        user = request.user

        if user.role != UserRole.ADMIN:
            return False

        admin_profile = getattr(user, "adminprofile", None)
        if not admin_profile:
            return False

        return admin_profile.admin_type in {
            AdminType.SCHOOL_OWNER,
            AdminType.PRINCIPAL,
        }


class IsPrincipalOrSchoolOwner(BasePermission):
    """
    Only principals and school owners are allowed
    to view teacher/student/admin lists.
    """

    def has_permission(self, request, view):
        user = request.user

        if not hasattr(user, "adminprofile"):
            return False

        return user.adminprofile.admin_type in [
            AdminType.PRINCIPAL,
            AdminType.SCHOOL_OWNER,
        ]



class CanManageSubjects(BasePermission):
    """
    Teachers + Admins can:
      - create
      - update

    Admins ONLY can delete.
    Students = read only.
    """

    def has_permission(self, request, view):
        user = request.user

        if not user.is_authenticated:
            return False

        # Read-only allowed for everyone
        if view.action in ["list", "retrieve"]:
            return True

        # Teachers & admins can modify
        if view.action in ["create", "update", "partial_update"]:
            return user.role in [UserRole.ADMIN, UserRole.TEACHER]

        # Only admin can delete
        if view.action == "destroy":
            return user.role == UserRole.ADMIN

        return False
