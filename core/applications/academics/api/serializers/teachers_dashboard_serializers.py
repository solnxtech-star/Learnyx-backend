import logging

from django.db import models
from django.db import transaction
from django.db.models import Max
from django.db.models import Sum
from rest_framework import serializers

from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import AssessmentType
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import StudentSubjectEnrollment
from core.applications.academics.models import Subject
from core.applications.academics.models import TeachingAssignment
from core.applications.grading.models import SubjectResult
from core.applications.users.models import StudentContact
from core.applications.users.models import StudentProfile

logger = logging.getLogger(__name__)


class TeacherSubjectSerializer(serializers.ModelSerializer):
    """
    Subjects taught by a teacher within a specific classroom context.
    """

    class Meta:
        model = Subject
        fields = [
            "id",
            "name",
            "code",
            "credit_hour",
            "is_mandatory",
        ]
        read_only_fields = fields



class TeacherClassroomSerializer(serializers.ModelSerializer):
    """
    Teacher Dashboard → Classrooms with subjects taught by the teacher
    in each classroom.

    Source of truth:
    - TeachingAssignment (NOT TeacherProfile.subjects/classrooms)
    """

    subjects = serializers.SerializerMethodField()

    class Meta:
        model = ClassRoom
        fields = [
            "id",
            "academic_class",
            "arm",
            "track",
            "subjects",
        ]
        read_only_fields = fields

    def get_subjects(self, classroom):
        """
        Returns subjects taught by the current teacher in the given classroom.
        """
        teacher = self.context.get("teacher")
        if teacher is None:
            return []

        subjects = (
            Subject.objects
            .filter(
                teaching_assignments__teacher=teacher,
                teaching_assignments__classroom=classroom,
            )
            .distinct()
            .order_by("name")
        )

        return TeacherSubjectSerializer(subjects, many=True).data

class ClassroomStudentSerializer(serializers.ModelSerializer):
    """
    Enhanced serializer for students visible to a teacher.
    Includes enrolled subjects and context-aware data.
    """

    full_name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    user_id = serializers.CharField(source="user.id", read_only=True)

    # Subjects this student is enrolled in that the teacher teaches
    enrolled_subjects = serializers.SerializerMethodField()

    # Additional useful fields
    gender_display = serializers.CharField(
        source="get_gender_display",
        read_only=True,
    )

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "student_id",
            "user_id",
            "full_name",
            "email",
            "current_class",
            "gender",
            "gender_display",
            "admission_date",
            "enrolled_subjects",
        ]
        read_only_fields = fields

    def get_enrolled_subjects(self, obj):
        """Get subjects this student is enrolled in that the teacher teaches"""
        request = self.context.get("request")
        session = self.context.get("session")
        term = self.context.get("term")

        if not all([request, session, term]):
            return []

        # Use prefetched enrollments if available
        enrollments = getattr(obj, "relevant_enrollments", None)

        if enrollments is None:
            # Fallback query if not prefetched
            teacher = request.user.teacherprofile
            subject_ids = teacher.teaching_assignments.filter(
                classroom_id=obj.classroom_id
            ).values_list("subject_id", flat=True)

            enrollments = obj.subject_enrollments.filter(
                session=session,
                term=term,
                subject_id__in=subject_ids
            ).select_related("subject")

        return [
            {
                "id": enrollment.subject.id,
                "name": enrollment.subject.name,
                "code": enrollment.subject.code,
                "enrollment_id": enrollment.id,
            }
            for enrollment in enrollments
        ]

class ClassroomMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassRoom
        fields = [
            "id",
            "academic_class",
            "arm",
            "track",
        ]


class StudentSubjectMatchSerializer(serializers.ModelSerializer):
    subjects = serializers.SerializerMethodField()
    student_name = serializers.CharField(source="user.name", read_only=True)
    # Get the active class from class_assignments
    classroom = serializers.SerializerMethodField()
    current_class = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "user",
            "student_name",
            "student_id",
            "current_class",
            "classroom",
            "subjects",
        ]

    def get_subjects(self, obj):
        teacher_subject_ids = self.context.get("teacher_subject_ids", [])
        student_subjects = obj.subject_enrollments.filter(
            subject_id__in=teacher_subject_ids,
        ).select_related("subject")
        return [se.subject.name for se in student_subjects]

    def get_classroom(self, obj):
        # Return the string representation of the active classroom (e.g., "JSS1 A")
        active_assignment = obj.class_assignments.filter(is_active=True).first()
        return str(active_assignment.classroom) if active_assignment else None

    def get_current_class(self, obj):
        # Return a structured representation of the current class
        active_assignment = obj.class_assignments.filter(is_active=True).first()
        if not active_assignment:
            return None
        classroom = active_assignment.classroom
        return {
            "academic_class": classroom.academic_class,
            "arm": classroom.arm,
            "track": classroom.track
        }
class TeacherClassroomStudentsResponseSerializer(serializers.Serializer):
    """Response wrapper for better API documentation"""
    classroom = serializers.CharField(help_text="Classroom name")
    classroom_id = serializers.CharField(help_text="Classroom ID")
    session = serializers.CharField(help_text="Academic session")
    term = serializers.CharField(help_text="Academic term")
    students = ClassroomStudentSerializer(many=True)
    total_students = serializers.CharField(
        help_text="Total number of students found"
    )

    def to_representation(self, instance):
        """Custom representation for clean API response"""
        data = super().to_representation(instance)
        data["meta"] = {
            "count": data["total_students"],
            "teacher_id": self.context.get("request").user.teacherprofile.id,
        }
        return data

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


class TeachersSubjectSerializer(serializers.ModelSerializer):
    classroom_id = serializers.IntegerField(source="classroom.id")
    classroom_name = serializers.CharField(source="classroom.__str__")

    subject_id = serializers.IntegerField(source="subject.id")
    subject_name = serializers.CharField(source="subject.name")
    subject_code = serializers.CharField(source="subject.code")

    class Meta:
        model = TeachingAssignment
        fields = (
            "classroom_id",
            "classroom_name",
            "subject_id",
            "subject_name",
            "subject_code",
        )

class AssessmentTypeSerializer(serializers.ModelSerializer):
    policy_id = serializers.IntegerField(source="policy.id")
    term_id = serializers.IntegerField(source="policy.term.id")

    class Meta:
        model = AssessmentType
        fields = (
            "id",
            "name",
            "category",
            "count",
            "weight",
            "max_score",
            "is_optional",
            "order",
            "policy_id",
            "term_id",
        )


class AssessmentValidationMixin:
    """
    Reusable domain validation logic for assessment entries.
    """

    def validate_student_subject_term(self, student, subject, assessment_type):
        policy = assessment_type.policy
        term = policy.term
        session = term.session

        if not term.is_active:
            raise serializers.ValidationError({
                "term": f"Term '{term.name}' is locked."
            })

        if not subject.class_rooms.filter(id=student.classroom_id).exists():
            raise serializers.ValidationError({
                "subject": (
                    f"{subject.name} is not assigned to "
                    f"{student.user.name}'s classroom."
                )
            })

        if not StudentSubjectEnrollment.objects.filter(
            student=student,
            subject=subject,
            session=session,
            term=term,
        ).exists():
            raise serializers.ValidationError({
                "enrollment": (
                    f"{student.user.name} is not enrolled in "
                    f"{subject.name} for this term."
                )
            })

    def validate_score(self, student, subject, assessment_type, score, instance=None):
        if score < 0:
            raise serializers.ValidationError({
                "score": "Score cannot be negative."
            })

        if score > assessment_type.max_score:
            raise serializers.ValidationError({
                "score": (
                    f"Score cannot exceed "
                    f"{assessment_type.max_score}."
                )
            })

        existing_total = (
            AssessmentRecord.objects.filter(
                student=student,
                classroom_subject=subject,
                assessment_type=assessment_type,
            ).aggregate(total=Sum("score"))["total"] or 0
        )

        if instance:
            existing_total -= instance.score

        max_total = assessment_type.max_score * assessment_type.count

        if existing_total + score > max_total:
            raise serializers.ValidationError({
                "score": (
                    f"Cumulative score cannot exceed {max_total} "
                    f"for this assessment type."
                )
            })

    def get_next_index(self, student, subject, assessment_type):
        last_index = (
            AssessmentRecord.objects.filter(
                student=student,
                classroom_subject=subject,
                assessment_type=assessment_type,
            ).aggregate(max_index=Max("index"))["max_index"] or 0
        )
        return last_index + 1

# -----------------------------
# Single entry serializer
# -----------------------------
class AssessmentEntryCreateSerializer(
    serializers.ModelSerializer,
    AssessmentValidationMixin
):
    student = serializers.PrimaryKeyRelatedField(
        queryset=StudentProfile.objects.all()
    )

    assessment_type = serializers.PrimaryKeyRelatedField(
        queryset=AssessmentType.objects.all()
    )

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

        self.validate_student_subject_term(student, subject, assessment_type)
        self.validate_score(
            student,
            subject,
            assessment_type,
            score,
            instance=getattr(self, "instance", None),
        )

        return attrs

    def create(self, validated_data):
        subject = validated_data.pop("subject")
        student = validated_data["student"]
        assessment_type = validated_data["assessment_type"]

        validated_data["classroom_subject"] = subject
        validated_data["index"] = self.get_next_index(
            student, subject, assessment_type
        )

        return AssessmentRecord.objects.create(**validated_data)

    def update(self, instance, validated_data):
        subject = validated_data.get("subject", instance.classroom_subject)
        student = validated_data.get("student", instance.student)
        assessment_type = validated_data.get(
            "assessment_type",
            instance.assessment_type,
        )
        score = validated_data.get("score", instance.score)

        self.validate_student_subject_term(student, subject, assessment_type)
        self.validate_score(
            student,
            subject,
            assessment_type,
            score,
            instance=instance,
        )

        instance.score = score
        instance.date_taken = validated_data.get(
            "date_taken",
            instance.date_taken,
        )
        instance.save()

        return instance

# -----------------------------
# Bulk entry serializer
# -----------------------------

class BulkAssessmentEntryItemSerializer(serializers.Serializer):
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=StudentProfile.objects.all(),
        source="student",
    )

    assessment_type_id = serializers.PrimaryKeyRelatedField(
        queryset=AssessmentType.objects.all(),
        source="assessment_type",
    )

    score = serializers.FloatField(min_value=0)
class BulkAssessmentEntrySerializer(
    serializers.Serializer,
    AssessmentValidationMixin
):
    subject_id = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.filter(is_active=True),
        source="subject",
    )

    entries = BulkAssessmentEntryItemSerializer(many=True)

    def validate(self, attrs):
        if not attrs["entries"]:
            raise serializers.ValidationError({
                "entries": "Entries list cannot be empty."
            })
        return attrs

    def create(self, validated_data):
        subject = validated_data["subject"]
        entries = validated_data["entries"]

        created_records = []

        with transaction.atomic():
            for entry in entries:
                student = entry["student"]
                assessment_type = entry["assessment_type"]
                score = entry["score"]

                self.validate_student_subject_term(
                    student, subject, assessment_type
                )

                self.validate_score(
                    student, subject, assessment_type, score
                )

                record = AssessmentRecord.objects.create(
                    student=student,
                    classroom_subject=subject,
                    assessment_type=assessment_type,
                    score=score,
                    index=self.get_next_index(
                        student,
                        subject,
                        assessment_type,
                    ),
                )

                created_records.append(record)

        return created_records
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
    weight = serializers.CharField(
        source="assessment_type.weight",
        read_only=True,
    )
    max_score = serializers.CharField(
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
