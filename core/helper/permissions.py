from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission

from core.applications.academics.models import ClassRoom
from core.applications.academics.models import TeachingAssignment
from core.applications.users.models import StudentProfile
from core.applications.users.models import User


class IsPrincipalOrSchoolOwner(BasePermission):
    """
    Full access: School Owner, Principal.
    Read-only: Teachers.
    Denied: HR, Bursar, Vice-Principal, Other admins, students.
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", None)

        if not user or not user.is_authenticated:
            return False

        # Teachers: READ-ONLY
        if user.role == "teacher":
            return request.method in SAFE_METHODS

        # Admins: only school_owner and principal
        if user.role == "admin":
            admin_profile = getattr(user, "adminprofile", None)
            if not admin_profile:
                return False
            return admin_profile.admin_type in ["school_owner", "principal"]

        # All other roles denied
        return False


class IsPrincipalOrSchoolOwnerForPolicies(BasePermission):
    """
    Principal / School Owner: full access
    Teachers: read-only (GET/HEAD/OPTIONS)
    Others: denied
    """

    def has_permission(self, request, view):
        user: User | None = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        # Teachers read-only
        if user.role == "teacher":
            return request.method in SAFE_METHODS

        # Admins: check adminprofile.admin_type
        if user.role == "admin":
            admin_profile = getattr(user, "adminprofile", None)
            if not admin_profile:
                return False
            return admin_profile.admin_type in ["school_owner", "principal"]

        return False


class IsPrincipalOwnerOrAssignedTeacher(BasePermission):
    """
    Allows:
    - School Owner and Principal: full access
    - Teachers: only if assigned to the classroom + subject
    - Others: denied

    This permission class expects:
    - `classroom_subject_id` in the request (Bulk entry, Record create)
    - OR class_room_id + subject_id in AssessmentEntry
    """

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        # --- Admins: allow if owner or principal ---
        if user.role == "admin":
            admin_type = getattr(user.adminprofile, "admin_type", None)
            return admin_type in ["school_owner", "principal"]

        # --- Teachers: require assignment check ---
        if user.role == "teacher":
            return True  # object-level check will finalize

        # All others denied (student/hr/bursar/etc)
        return False

    def has_object_permission(self, request, view, obj):
        """
        Used for AssessmentRecordViewSet.
        The `obj` is an AssessmentRecord instance.
        """
        user = request.user

        # Principal/Owner → always allowed
        if user.role == "admin":
            admin_type = getattr(user.adminprofile, "admin_type", None)
            return admin_type in ["school_owner", "principal"]

        if user.role != "teacher":
            return False

        # Teachers → must be assigned to this classroom_subject
        return TeachingAssignment.objects.filter(
            id=obj.classroom_subject_id,
            teacher=user,
            school=user.school,
        ).exists()


class IsSchoolAdminOrAssignedTeacher(BasePermission):
    """
    Enterprise-grade permission for Teacher Dashboard.

    Access Rules:
    - School Owners & Principals: Full access
    - Teachers: Limited to assigned classrooms & students
    - Others: No access
    """

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        # Admin: School Owner / Principal
        if user.role == "admin":
            admin_type = getattr(user.adminprofile, "admin_type", None)
            return admin_type in ["school_owner", "principal"]

        # Teachers allowed – object level check will restrict
        if user.role == "teacher":
            return True

        return False

    def has_object_permission(self, request, view, obj):
        user = request.user

        # Admins: always allowed
        if user.role == "admin":
            admin_type = getattr(user.adminprofile, "admin_type", None)
            return admin_type in ["school_owner", "principal"]

        # Teachers
        if user.role != "teacher":
            return False

        # If object is a classroom
        if isinstance(obj, ClassRoom):
            return TeachingAssignment.objects.filter(
                teacher=user,
                classroom=obj,
                school=user.school,
            ).exists()

        # If object is a student profile
        if isinstance(obj, StudentProfile):
            return TeachingAssignment.objects.filter(
                teacher=user,
                classroom=obj.classroom,
                school=user.school,
            ).exists()

        return False
