import logging

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.applications.academics.models import ClassRoom
from core.applications.users.models import AdminProfile
from core.applications.users.models import StudentProfile
from core.applications.users.models import TeacherProfile
from core.applications.users.services.profile_activation import ProfileActivationService
from core.helper.enums import AcademicClass
from core.helper.enums import AcademicTrack
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

    # --------------------------------------------------
    # Validation
    # --------------------------------------------------
    def validate(self, attrs):
        request = self.context.get("request")
        if request is None:
            raise ValidationError(_("Request is required in serializer context."))

        profile_id = self.context.get("profile_id")
        if not profile_id:
            raise ValidationError({"id": _("Profile ID is required in URL parameter.")})

        model = self.MODEL_MAP[attrs["type"]]

        instance = (
            model.objects
            .select_related("user", "user__school")
            .filter(id=profile_id)
            .first()
        )

        if not instance:
            raise ValidationError(
                {"id": _("Profile not found for the given type.")},
            )

        # Multi-tenancy guard
        if instance.school != request.user.school:
            raise ValidationError(
                _("You do not have permission to manage profiles outside your school."),
            )

        # Defensive guard (also enforced in service)
        if (
            instance.status == AdmissionStatus.APPROVED
            and attrs["action"] == "approve"
        ):
            raise ValidationError(_("Profile is already approved."))

        attrs["instance"] = instance
        return attrs

    # --------------------------------------------------
    # Delegation only
    # --------------------------------------------------
    def save(self, **kwargs):
        return ProfileActivationService.activate(
            profile=self.validated_data["instance"],
            action=self.validated_data["action"],
            actor=self.context["request"].user,
            reason=self.validated_data.get("reason", ""),
        )

class ClassRoomCreateSerializer(serializers.ModelSerializer):
    """
    Serializer used for creating and updating classrooms.

    - School is auto-assigned from the authenticated admin.
    - Academic track (Science / Arts / Commercial) is selected explicitly.
    """

    academic_class = serializers.ChoiceField(
        choices=AcademicClass.choices,
    )

    track = serializers.ChoiceField(
        choices=AcademicTrack.choices,
        help_text="Academic track for the classroom (Science, Arts, Commercial)",
    )

    class Meta:
        model = ClassRoom
        fields = ["id", "academic_class", "arm", "track"]
        extra_kwargs = {
            "arm": {"required": True},
            "track": {"required": True},
        }

    def validate(self, attrs):
        request = self.context["request"]
        school = getattr(request.user, "school", None)

        if not school:
            error_message = _("User does not belong to any school.")
            raise serializers.ValidationError(error_message)

        # Enforce school-level uniqueness (academic_class + arm + track)
        if ClassRoom.objects.filter(
            school=school,
            academic_class=attrs["academic_class"],
            arm=attrs["arm"],
            track=attrs["track"],
        ).exists():
            msg = f"{attrs['academic_class']} {attrs['arm']} ({attrs['track']}) already exists."  # noqa: E501
            raise serializers.ValidationError(
                msg,
            )

        return attrs

    def create(self, validated_data):
        school = self.context["request"].user.school
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

    track_display = serializers.CharField(
        source="get_track_display",
        read_only=True,
    )

    class Meta:
        model = ClassRoom
        fields = [
            "id",
            "academic_class",
            "class_display",
            "arm",
            "track",
            "track_display",
            "created_at",
            "updated_at",
        ]
