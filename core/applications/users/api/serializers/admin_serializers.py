from rest_framework import serializers
from core.applications.users.models import AdminProfile, StudentProfile, TeacherProfile
from core.helper.enums import AdmissionStatus

from django.utils.translation import gettext_lazy as _


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
        "id": 12,
        "action": "approve",
        "reason": "Documents verified"
    }
    """

    type = serializers.ChoiceField(
        choices=["student", "teacher", "admin"], help_text=_("Profile type")
    )
    id = serializers.IntegerField(help_text=_("Profile ID"))
    action = serializers.ChoiceField(
        choices=["approve", "reject"], help_text=_("Action to perform")
    )
    reason = serializers.CharField(
        required=False, allow_blank=True, help_text=_("Optional reason")
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
        model = self.MODEL_MAP[attrs["type"]]
        instance = model.objects.select_related("user").filter(id=attrs["id"]).first()
        if not instance:
            raise serializers.ValidationError(
                {"id": _("Profile not found for the given type.")}
            )

        request = self.context.get("request")
        if request is None:
            raise serializers.ValidationError(
                _("Request is required in serializer context.")
            )

        # Multi-tenancy check
        if instance.school != request.user.school:
            raise serializers.ValidationError(
                _("You do not have permission to manage profiles outside your school.")
            )

        # Prevent double approve
        if instance.status == AdmissionStatus.APPROVED and attrs["action"] == "approve":
            raise serializers.ValidationError(_("Profile is already approved."))

        attrs["instance"] = instance
        return attrs

    def save(self):
        instance = self.validated_data["instance"]
        action = self.validated_data["action"]
        request = self.context["request"]

        instance.status = (
            AdmissionStatus.APPROVED
            if action == "approve"
            else AdmissionStatus.REJECTED
        )
        instance.approved_by = (
            request.user.email or request.user.name or str(request.user.id)
        )
        instance.save(update_fields=["status", "approved_by"])
        return instance
