from django.db import models
from django.db import transaction
from rest_framework import serializers

from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import Subject
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
    Teacher input serializer for assessment entry.

    Guarantees:
    - Subject belongs to student's classroom
    - Score respects assessment max_score
    - classroom_subject is stored correctly
    - index is auto-incremented per student + subject + assessment_type
    """

    subject = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.filter(is_active=True),
        write_only=True,
    )

    class Meta:
        model = AssessmentRecord
        fields = (
            "student",
            "assessment_type",
            "subject",
            "score",
            "date_taken",
        )

    def validate(self, attrs):
        student = attrs["student"]
        subject = attrs["subject"]
        assessment_type = attrs["assessment_type"]
        score = attrs["score"]

        # 1️⃣ Subject must be assigned to student's classroom
        if not subject.class_rooms.filter(
            id=student.classroom_id,
        ).exists():
            raise serializers.ValidationError(
                {
                    "subject": (
                        "This subject is not assigned "
                        "to the student's classroom."
                    ),
                },
            )

        # 2️⃣ Score bounds
        if score < 0:
            raise serializers.ValidationError(
                {"score": "Score cannot be negative."},
            )

        if score > assessment_type.max_score:
            raise serializers.ValidationError(
                {
                    "score": (
                        f"Score cannot exceed "
                        f"{assessment_type.max_score}."
                    ),
                },
            )

        return attrs

    def create(self, validated_data):
        subject = validated_data.pop("subject")
        student = validated_data["student"]
        assessment_type = validated_data["assessment_type"]

        # 3️⃣ Index auto-increment
        last_index = (
            AssessmentRecord.objects.filter(
                student=student,
                classroom_subject=subject,
                assessment_type=assessment_type,
            )
            .aggregate(
                max_index=models.Max("index")
            )
            .get("max_index")
            or 0
        )

        validated_data["index"] = last_index + 1
        validated_data["classroom_subject"] = subject

        return AssessmentRecord.objects.create(**validated_data)



class AssessmentEntrySerializer(serializers.ModelSerializer):
    """
    Read-only serializer for assessment records.
    """

    subject_id = serializers.UUIDField(
        source="classroom_subject.id",
        read_only=True,
    )
    subject_name = serializers.CharField(
        source="classroom_subject.name",
        read_only=True,
    )

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
        fields = (
            "id",
            "subject_id",
            "subject_name",
            "assessment_name",
            "category",
            "weight",
            "max_score",
            "score",
            "percentage",
            "date_taken",
        )
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
