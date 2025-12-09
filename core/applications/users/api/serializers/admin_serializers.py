from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
import logging
from core.applications.academics.models import ClassRoom
from core.applications.users.models import AdminProfile
from core.applications.users.models import StudentProfile
from core.applications.users.models import TeacherProfile
from core.helper.enums import AcademicClass
from core.helper.enums import AdmissionStatus

logger = logging.getLogger(__name__)


class StudentProfileListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing student profiles along with linked user information.
    Used in admin listing views.
    """

    email = serializers.EmailField(source="user.email")
    name = serializers.CharField(source="user.name")
    phone_number = serializers.CharField(source="user.phone_number")

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "email",
            "name",
            "phone_number",
            "status",
            "student_id",
            "gender",
            "current_class",
            "guardian_name",
            "guardian_phone",
            "admission_date",
            "approved_by",
        ]


class TeacherProfileListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing teachers with full profile details
    including their professional and departmental information.
    """

    email = serializers.EmailField(source="user.email")
    name = serializers.CharField(source="user.name")
    phone_number = serializers.CharField(source="user.phone_number")

    class Meta:
        model = TeacherProfile
        fields = [
            "id",
            "email",
            "name",
            "phone_number",
            "status",
            "staff_id",
            "qualification",
            "specialization",
            "department",
            "approved_by",
        ]


class AdminProfileListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing admin profiles within a school.
    """

    email = serializers.EmailField(source="user.email")
    name = serializers.CharField(source="user.name")

    class Meta:
        model = AdminProfile
        fields = [
            "id",
            "email",
            "name",
            "admin_type",
            "position",
            "school_name",
            "status",
            "approved_by",
        ]


class UserActivationSerializer(serializers.Serializer):
    """
    Serializer to approve/reject a profile (student, teacher, admin).

    Payload example:
    {
        "type": "student",
        "action": "approve",
        "reason": "Documents verified"
    }
    """

    type = serializers.ChoiceField(
        choices=["student", "teacher", "admin"],
        help_text=_("Profile type"),
    )
    # REMOVED: id field since we get it from URL parameter
    action = serializers.ChoiceField(
        choices=["approve", "reject"],
        help_text=_("Action to perform"),
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text=_("Optional reason"),
    )

    MODEL_MAP = {
        "student": StudentProfile,
        "teacher": TeacherProfile,
        "admin": AdminProfile,
    }

    def validate(self, attrs):
        """
        Validate that:
         - the profile exists
         - the profile belongs to the request user's school (multi-tenancy)
         - we don't re-approve an already approved profile
        """
        request = self.context.get("request")
        if request is None:
            raise serializers.ValidationError(
                _("Request is required in serializer context."),
            )

        # Get profile_id from URL parameter (passed from view)
        profile_id = self.context.get('profile_id')
        if not profile_id:
            raise serializers.ValidationError(
                {"id": _("Profile ID is required in URL parameter.")},
            )

        logger.info(f"Starting validation for type: {attrs['type']}, id: {profile_id}")

        model = self.MODEL_MAP[attrs["type"]]

        # Get instance with user and school data prefetched
        instance = (
            model.objects.select_related("user", "user__school")
            .filter(id=profile_id)
            .first()
        )

        if not instance:
            logger.error(f"Profile not found. ID: {profile_id}")
            raise serializers.ValidationError(
                {"id": _("Profile not found for the given type.")},
            )

        logger.info(f"Found profile: {instance.id}")

        # Multi-tenancy check
        if instance.school != request.user.school:
            logger.error(
                f"School mismatch: user school {request.user.school.id} != instance school {instance.school.id}"
            )
            raise serializers.ValidationError(
                _("You do not have permission to manage profiles outside your school."),
            )

        logger.info(f"Current profile status: {instance.status}")
        logger.info(f"Requested action: {attrs['action']}")

        # Prevent double approve
        if instance.status == AdmissionStatus.APPROVED and attrs["action"] == "approve":
            logger.error("Attempting to approve already approved profile")
            raise serializers.ValidationError(_("Profile is already approved."))

        attrs["instance"] = instance
        attrs["profile_id"] = profile_id
        logger.info("Validation successful")
        return attrs

    def save(self):
        logger.info("Starting save operation")
        instance = self.validated_data["instance"]
        action = self.validated_data["action"]
        reason = self.validated_data.get("reason", "")
        request = self.context["request"]

        logger.info(f"Updating profile {instance.id} to status: {action}")

        instance.status = (
            AdmissionStatus.APPROVED
            if action == "approve"
            else AdmissionStatus.REJECTED
        )
        instance.approved_by = (
            request.user.email or request.user.name or str(request.user.id)
        )

        logger.info(
            f"New status: {instance.status}, approved_by: {instance.approved_by}"
        )
        instance.save(update_fields=["status", "approved_by"])

        # Send email notification (in background if possible, or async)
        try:
            from core.applications.users.utils.email_utils import send_approval_notification
            send_approval_notification(instance, action, reason)
            logger.info(f"Notification email sent to {instance.user.email}")
        except Exception as e:
            logger.error(f"Failed to send notification email: {str(e)}")
            # Don't fail the whole operation if email fails

        logger.info("Save operation completed successfully")
        return instance
class ClassRoomCreateSerializer(serializers.ModelSerializer):
    """
    Serializer used for creating and updating classrooms.
    School is auto-assigned based on the authenticated admin.
    """

    academic_class = serializers.ChoiceField(choices=AcademicClass.choices)

    class Meta:
        model = ClassRoom
        fields = ["id", "academic_class", "arm"]
        extra_kwargs = {
            "arm": {"required": True},
        }

    def validate(self, attrs):
        request = self.context["request"]
        school = getattr(request.user, "school", None)

        if not school:
            raise serializers.ValidationError("User does not belong to any school.")

        # Enforce school-level uniqueness before save()
        if ClassRoom.objects.filter(
            school=school,
            academic_class=attrs["academic_class"],
            arm=attrs["arm"],
        ).exists():
            raise serializers.ValidationError(
                f"ClassRoom {attrs['academic_class']} {attrs['arm']} already exists.",
            )

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        school = request.user.school

        return ClassRoom.objects.create(
            school=school,
            **validated_data,
        )


class ClassRoomSerializer(serializers.ModelSerializer):
    """
    Read serializer for listing and retrieving classrooms.
    """

    class_display = serializers.CharField(
        source="get_academic_class_display",
        read_only=True,
    )

    class Meta:
        model = ClassRoom
        fields = [
            "id",
            "academic_class",
            "class_display",
            "arm",
            "created_at",
            "updated_at",
        ]
