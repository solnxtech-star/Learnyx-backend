from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _


class AccessService:

    @staticmethod
    def is_school_admin(user):
        """
        Check if the user is a school owner or principal.
        This method centralizes the logic for determining if a user has
        administrative access to school-level resources.
        Returns:
            bool: True if the user is a school owner or principal, False otherwise.
        """
        if user.role != "admin":
            return False

        admin_type = getattr(user.adminprofile, "admin_type", None)
        return admin_type in ["school_owner", "principal"]

    @staticmethod
    def enforce_admin(user):
        """
        Enforce that the user is a school owner or principal.
        Raises:
            PermissionDenied: If the user is not a school owner or principal.
        """

        if not AccessService.is_school_admin(user):
            raise PermissionDenied(_("Only school owners/principals can perform this action."))

    @staticmethod
    def enforce_school(user, obj):
        """
        Enforce that the user can only access resources from their school.
        This method should be called in views or serializers to ensure that users
        cannot access or modify resources that belong to a different school.
        Args:
            user: The user object.
            obj: The object to check access for.
        Raises:
            PermissionDenied: If the user is not from the same school as the object.
        """
        if obj.school != getattr(user, "school", None):
            raise PermissionDenied(_("You can only access resources from your school."))
