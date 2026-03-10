import logging

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.applications.academics.models import AcademicSession
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import StudentClassAssignment
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
    Serializer for creating and updating classrooms.

    Features:
    - Automatically assigns the authenticated user's school.
    - Ensures academic_class + arm + track is unique within the school.
    - Optional assignment of a form_teacher who must belong to the same school.
    """

    academic_class = serializers.ChoiceField(
        choices=AcademicClass.choices,
        help_text=_("Parent academic class, e.g., JSS1, SS2"),
    )

    track = serializers.ChoiceField(
        choices=AcademicTrack.choices,
        help_text=_("Academic track for the classroom (Science, Arts, Commercial)"),
    )

    form_teacher = serializers.PrimaryKeyRelatedField(
        queryset=TeacherProfile.objects.all(),
        required=False,
        allow_null=True,
        help_text=_("Optional: Assign a teacher as the form teacher"),
    )

    class Meta:
        model = ClassRoom
        fields = ["id", "academic_class", "arm", "track", "form_teacher"]
        extra_kwargs = {
            "arm": {"required": True},
            "track": {"required": True},
        }

    def validate(self, attrs):
        """Ensure school-scoped uniqueness and valid form_teacher."""
        request = self.context["request"]
        school = getattr(request.user, "school", None)
        if not school:
            raise serializers.ValidationError(_("User does not belong to any school."))

        # Use existing instance values if fields are not provided (for updates)
        academic_class = attrs.get("academic_class", getattr(self.instance, "academic_class", None))
        arm = attrs.get("arm", getattr(self.instance, "arm", None))
        track = attrs.get("track", getattr(self.instance, "track", None))

        # Check uniqueness within school
        qs = ClassRoom.objects.filter(school=school, academic_class=academic_class, arm=arm, track=track)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"{academic_class} {arm} ({track}) already exists in this school."
            )

        # Validate that form_teacher belongs to the same school
        form_teacher = attrs.get("form_teacher")
        if form_teacher and form_teacher.user.school != school:
            raise serializers.ValidationError(_("Form teacher must belong to the same school."))

        return attrs

    def create(self, validated_data):
        """Auto-assign the school when creating a classroom."""
        validated_data["school"] = self.context["request"].user.school
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Explicit update for clarity and control."""
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ClassRoomSerializer(serializers.ModelSerializer):
    """
    Serializer for listing and retrieving classrooms.

    Includes:
    - Human-readable class and track display.
    - Total subjects and students in the classroom for the active session.
    - Form teacher's name.
    """

    class_display = serializers.CharField(source="get_academic_class_display", read_only=True)
    track_display = serializers.CharField(source="get_track_display", read_only=True)
    form_teacher_name = serializers.CharField(source="form_teacher.user.name", read_only=True)
    total_subjects = serializers.SerializerMethodField()
    total_students = serializers.SerializerMethodField()

    class Meta:
        model = ClassRoom
        fields = [
            "id",
            "academic_class",
            "class_display",
            "arm",
            "track",
            "track_display",
            "form_teacher_name",
            "total_subjects",
            "total_students",
            "created_at",
            "updated_at",
        ]

    def get_total_subjects(self, obj):
        """Return count of active subjects assigned to the classroom."""
        return obj.subjects.filter(is_active=True).count()

    def get_total_students(self, obj):
        """Return count of active students in the classroom for the current academic session."""
        active_session = AcademicSession.objects.filter(school=obj.school, is_active=True).first()
        if not active_session:
            return 0

        return StudentClassAssignment.objects.filter(
            classroom=obj,
            academic_session=active_session,
            is_active=True
        ).count()
