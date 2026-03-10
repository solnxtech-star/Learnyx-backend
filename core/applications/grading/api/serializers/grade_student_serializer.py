from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.applications.grading.models import GradeScale
from core.applications.users.models import StudentProfile


class GradingKeySerializer(serializers.ModelSerializer):
    """
    Serializer for grading key/scale for inclusion in reports.
    Shows the school's grading system at a glance.

    Example Output:
        [
            {"grade": "A", "min_score": 75, "max_score": 100, "point": 5.0},
            {"grade": "B", "min_score": 70, "max_score": 74, "point": 4.0},
            ...
        ]
    """

    score_range = serializers.SerializerMethodField(
        help_text=_("Formatted score range (e.g., '75-100')"),
    )

    class Meta:
        model = GradeScale
        fields = ["grade", "display_name", "score_range", "point", "remark"]

    def get_score_range(self, obj):
        """Format score range for display."""
        return f"{obj.min_score}-{obj.max_score}"

class StudentListSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    classroom = serializers.CharField(source="classroom.name", read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "student_id",
            "name",
            "email",
            "classroom",
            "current_class",
            "status",
            "admission_date",
        ]


class StudentDetailSerializer(serializers.ModelSerializer):
    # User info
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    role = serializers.CharField(source="user.get_role_display", read_only=True)

    # Classroom
    classroom = serializers.CharField(source="classroom.name", read_only=True)

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "student_id",

            # User
            "name",
            "email",
            "phone_number",
            "role",

            # Academic
            "classroom",
            "current_class",
            "admission_date",

            # Personal
            "gender",
            "guardian_name",
            "guardian_phone",
            "address",

            # Approval
            "status",
            "approved_by",

            "created_at",
            "updated_at",
        ]
