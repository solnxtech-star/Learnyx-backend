from rest_framework import serializers

from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import ClassRoom
from core.applications.grading.models import SubjectResult
from core.applications.users.models import StudentContact
from core.applications.users.models import StudentProfile


class TeacherClassroomSerializer(serializers.ModelSerializer):
    """
    Teacher Dashboard → Assigned Classrooms
    """

    class Meta:
        model = ClassRoom
        fields = ["id", "academic_class", "arm"]
        read_only_fields = fields


class ClassroomStudentSerializer(serializers.ModelSerializer):
    """
    Classroom → Student List.
    """

    full_name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

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
    Student Profile View (Teacher/Admin)
    """

    full_name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

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




class AssessmentEntryCreateSerializer(serializers.ModelSerializer):
    """
    PRD: Teacher enters or updates student assessment scores
    WRITE serializer only
    this is not used for reading/displaying scores
    """

    class Meta:
        model = AssessmentRecord
        fields = [
            "student",
            "assessment_type",
            "score",
            "date_taken",
        ]

    def validate(self, attrs):
        """
        Light validation only.
        Business rules (max_score, ownership, duplicates)
        live in the Service layer.
        """
        if attrs["score"] < 0:
            msg = "Score cannot be negative."
            raise serializers.ValidationError(msg)
        return attrs



class AssessmentEntrySerializer(serializers.ModelSerializer):
    """
    results_entries
    Raw assessment scores per subject.
    """

    assessment_name = serializers.CharField(
        source="assessment_type.name",
        read_only=True,
    )
    category = serializers.CharField(
        source="assessment_type.category",
        read_only=True,
    )
    weight = serializers.IntegerField(
        source="assessment_type.weight",
        read_only=True,
    )
    max_score = serializers.IntegerField(
        source="assessment_type.max_score",
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
            "category",
            "weight",
            "max_score",
            "score",
            "percentage",
            "date_taken",
        ]
        read_only_fields = fields



class SubjectResultSerializer(serializers.ModelSerializer):
    """
    PRD: results_computed
    Fully computed subject result for a student
    """

    subject = serializers.CharField(
        source="classroom_subject.subject.name",
        read_only=True,
    )

    class Meta:
        model = SubjectResult
        fields = [
            "subject",
            "total_ca",
            "exam_score",
            "half_term_score",
            "total_score",
            "average_score",
            "grade",
            "grade_point",
            "remark",
            "target_grade",
            "target_point",
        ]
        read_only_fields = fields


class StudentSubjectResultSerializer(serializers.Serializer):
    """
    PRD: Student → Subject → Assessments + Computed Result
    """

    subject = serializers.CharField()
    assessments = AssessmentEntrySerializer(many=True)
    computed_result = SubjectResultSerializer()




class ResultSnapshotSerializer(serializers.Serializer):
    """
    Frozen report metadata (PDF/Export)
    """

    term = serializers.CharField()
    class_name = serializers.CharField()
    generated_at = serializers.DateTimeField()
    file_url = serializers.URLField()


# ============================================================
# STUDENT CONTACTS / GUARDIANS
# ============================================================

class StudentContactSerializer(serializers.ModelSerializer):
    """
    PRD: Student Guardian / Contact Info
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
