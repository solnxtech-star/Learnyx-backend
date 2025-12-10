from rest_framework import serializers

from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import ClassRoom
from core.applications.users.models import StudentContact
from core.applications.users.models import StudentProfile


class TeacherClassroomSerializer(serializers.ModelSerializer):
    """
    Serializer for listing classrooms assigned to a teacher.

    Purpose:
        Used in the Teacher Dashboard to show all classrooms
        linked to the logged-in teacher.

    Fields:
        - id: Unique classroom identifier
        - academic_class: Class level (e.g. JSS1, SS2)
        - arm: Class stream/arm (A, B, C)
    """

    class Meta:
        model = ClassRoom
        fields = [
            "id",
            "academic_class",
            "arm",
        ]
        read_only_fields = fields


class ClassroomStudentSerializer(serializers.ModelSerializer):
    """
    Serializer for listing students inside a classroom.

    Purpose:
        Lightweight serializer used to render class lists
        for teachers.

    Includes:
        - User identity data (name, email)
        - Student identification data
    """

    full_name = serializers.CharField(
        source="user.name",
        read_only=True,
    )

    email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "student_id",
            "full_name",
            "email",
            "current_class",
        ]
        read_only_fields = fields


class StudentProfileDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for fetching a student's full profile.

    Used when a teacher/admin opens a specific student's profile view.
    """

    full_name = serializers.CharField(
        source="user.name",
        read_only=True,
    )

    email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "student_id",
            "full_name",
            "email",
            "gender",
            "current_class",
            "admission_date",
            "guardian_name",
            "guardian_phone",
            "address",
        ]
        read_only_fields = fields


class StudentAssessmentSerializer(serializers.ModelSerializer):
    """
    Serializer for student assessment results.
    """

    assessment_name = serializers.CharField(
        source="assessment_type.name",
        read_only=True,
    )

    percentage = serializers.FloatField(
        source="percentage_score",
        read_only=True,
    )

    class Meta:
        model = AssessmentRecord
        fields = [
            "id",
            "assessment_name",
            "index",
            "score",
            "percentage",
            "date_taken",
        ]
        read_only_fields = fields


class StudentContactSerializer(serializers.ModelSerializer):
    """
    Serializer for student guardian/contact information.
    """

    class Meta:
        model = StudentContact
        fields = [
            "id",
            "name",
            "relationship",
            "phone",
            "email",
            "is_primary",
        ]
        read_only_fields = fields
