from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from rest_framework import serializers

from core.applications.academics.models import AcademicSession, AssessmentType
from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import StudentSubjectEnrollment
from core.applications.academics.models import Subject
from core.applications.academics.models import TeachingAssignment
from core.applications.users.models import StudentEnrollment
from core.applications.users.models import StudentProfile
from core.applications.users.models import User


class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email"]


class ClassroomMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassRoom
        fields = ["id", "academic_class", "arm"]


class StudentCurrentClassSerializer(serializers.ModelSerializer):
    """
    Serializer for student's current class information.
    """
    user = UserMiniSerializer()
    classroom = ClassroomMiniSerializer()

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "student_id",
            "user",
            "current_class",
            "classroom",
        ]

class StudentEnrollmentSerializer(serializers.ModelSerializer):
    """
    Serializer for student's enrollment history.
    """
    classroom = ClassroomMiniSerializer()
    session = serializers.StringRelatedField()
    term = serializers.StringRelatedField()

    class Meta:
        model = StudentEnrollment
        fields = [
            "id",
            "classroom",
            "session",
            "term",
            "is_active",
        ]

class StudentListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing students with minimal details.
    """
    user = UserMiniSerializer()
    current_classroom = ClassroomMiniSerializer(source="classroom")

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "student_id",
            "user",
            "current_class",
            "current_classroom",
        ]

class StudentDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed student information including enrollment history.
    """
    user = UserMiniSerializer()
    classroom = ClassroomMiniSerializer()
    enrollments = StudentEnrollmentSerializer(many=True)

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "student_id",
            "user",
            "gender",
            "current_class",
            "classroom",
            "enrollments",
        ]

class AdminAssignSubjectsToStudentSerializer(serializers.Serializer):
    """
    Admin assigns subjects to a student for a specific session and term.

    Behavior:
        - Replaces all existing subject assignments
        - Enforced per school
    """

    subject_ids = serializers.ListField(
        child=serializers.CharField(),
    )
    session_id = serializers.CharField()
    term_id = serializers.CharField()

    def validate_subject_ids(self, subject_ids):
        school = self.context["request"].user.school
        subjects = Subject.objects.filter(id__in=subject_ids, school=school)

        if subjects.count() != len(subject_ids):
            msg = "Some subjects do not exist or do not belong to your school."
            raise serializers.ValidationError(
                msg,
            )
        return subject_ids

    def validate(self, attrs):
        school = self.context["request"].user.school
        session_id = attrs["session_id"]
        term_id = attrs["term_id"]

        # Validate session
        try:
            session = AcademicSession.objects.get(id=session_id, school=school)
        except AcademicSession.DoesNotExist:
            raise serializers.ValidationError({
                "session_id": (
                    "Invalid session ID or session does not belong to your school."
                ),
            }) from None

        # Validate term existence
        try:
            term = AcademicTerm.objects.get(id=term_id)
        except AcademicTerm.DoesNotExist:
            raise serializers.ValidationError({
                "term_id": "Invalid term ID.",
            }) from None

        # Validate term belongs to the provided session
        if term.session_id != session.id:
            raise serializers.ValidationError({
                "term_id": "The specified term does not belong to the provided session."
            })

        # Store the objects for use in save()
        attrs["session"] = session
        attrs["term"] = term
        return attrs

    def save(self, student):
        admin = self.context["request"].user
        session = self.validated_data["session"]
        term = self.validated_data["term"]
        subject_ids = self.validated_data["subject_ids"]

        # Remove previous assignments for this student, session, and term
        StudentSubjectEnrollment.objects.filter(
            student=student,
            session=session,
            term=term,
        ).delete()

        # Get all subjects again to ensure they belong to school
        school = admin.school
        subjects = Subject.objects.filter(id__in=subject_ids, school=school)

        if subjects.count() != len(subject_ids):
            raise serializers.ValidationError(
                "Some subjects do not exist or do not belong to your school."
            )

        # Create new enrollments
        enrollments = [
            StudentSubjectEnrollment(
                student=student,
                subject=subject,
                session=session,
                term=term,
                assigned_by=admin,
            )
            for subject in subjects
        ]

        StudentSubjectEnrollment.objects.bulk_create(enrollments)
        return enrollments



# ----------------------------------------
# Single Assessment Record Serializer
# ----------------------------------------
class AssessmentRecordSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and managing individual assessment records.

    Validations:
    - Student must be enrolled in the subject for the current session & term.
    - Score must be within assessment type max score.
    - Index must be within assessment type allowed count.
    """

    student_name = serializers.CharField(source="student.user.name", read_only=True)
    student_id = serializers.CharField(source="student.student_id", read_only=True)
    subject_name = serializers.CharField(
        source="classroom_subject.subject.name", read_only=True
    )
    assessment_type_name = serializers.CharField(
        source="assessment_type.name", read_only=True,
    )
    percentage_score = serializers.FloatField(read_only=True)

    class Meta:
        model = AssessmentRecord
        fields = [
            "id",
            "student",
            "student_name",
            "student_id",
            "classroom_subject",
            "subject_name",
            "assessment_type",
            "assessment_type_name",
            "index",
            "score",
            "percentage_score",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "percentage_score", "created_at", "updated_at"]

    def validate(self, data):
        student = data.get("student")
        classroom_subject = data.get("classroom_subject")
        assessment_type = data.get("assessment_type")
        index = data.get("index")
        score = data.get("score")

        # Validate teaching assignment
        if not isinstance(classroom_subject, TeachingAssignment):
            raise serializers.ValidationError({
                "classroom_subject": "Invalid teaching assignment."
            })

        # Validate student enrollment in subject for session & term
        if not StudentSubjectEnrollment.objects.filter(
            student=student,
            subject=classroom_subject.subject,
            session=classroom_subject.session,
            term=classroom_subject.term,
        ).exists():
            raise serializers.ValidationError({
                "student": f"{student} is not enrolled in {classroom_subject.subject} for this session/term.",  # noqa: E501
            })

        # Validate index
        if index < 1 or index > assessment_type.max_assessments:
            raise serializers.ValidationError({
                "index": f"Index must be between 1 and {assessment_type.max_assessments}.",  # noqa: E501
            })

        # Validate score
        if score < 0 or score > assessment_type.max_score:
            raise serializers.ValidationError({
                "score": f"Score must be between 0 and {assessment_type.max_score}.",
            })

        return data

    def create(self, validated_data):
        score = validated_data["score"]
        max_score = validated_data["assessment_type"].max_score
        validated_data["percentage_score"] = float(
            Decimal(score) / Decimal(max_score) * 100,
        )
        return super().create(validated_data)


# ----------------------------------------
# Assessment Entry Form Data Serializer
# ----------------------------------------
class AssessmentEntryFormDataSerializer(serializers.Serializer):
    """
    Validates classroom and subject selection for assessment forms.
    """

    class_room_id = serializers.IntegerField()
    subject_id = serializers.IntegerField()

    def validate(self, data):
        user = self.context["request"].user

        # Validate classroom
        try:
            classroom = user.school.classrooms.get(id=data["class_room_id"])
        except ObjectDoesNotExist:
            raise serializers.ValidationError({"class_room_id": "Invalid classroom."})

        # Validate subject
        try:
            subject = user.school.subjects.get(id=data["subject_id"], is_active=True)
        except ObjectDoesNotExist:
            raise serializers.ValidationError({"subject_id": "Invalid or inactive subject."})

        data["class_room"] = classroom
        data["subject"] = subject
        return data


# ----------------------------------------
# Single Student Score Entry Serializer
# ----------------------------------------
class StudentScoreEntrySerializer(serializers.Serializer):
    """
    Represents a single student score for bulk assessment upload.
    """

    student_id = serializers.IntegerField()
    score = serializers.FloatField(min_value=0)

    def validate(self, data):
        if data["score"] < 0:
            raise serializers.ValidationError({"score": "Score cannot be negative."})
        return data


# ----------------------------------------
# Bulk Assessment Entry Serializer
# ----------------------------------------
class BulkAssessmentEntrySerializer(serializers.Serializer):
    """
    Handles bulk creation or update of assessment records.
    """

    classroom_subject_id = serializers.IntegerField()
    assessment_type_id = serializers.IntegerField()
    index = serializers.IntegerField(min_value=1)
    entries = serializers.ListField(child=StudentScoreEntrySerializer(), min_length=1)

    def validate(self, data):
        user = self.context["request"].user
        classroom_subject_id = data["classroom_subject_id"]
        assessment_type_id = data["assessment_type_id"]
        index = data["index"]
        entries = data["entries"]

        # Validate teaching assignment
        try:
            classroom_subject = TeachingAssignment.objects.select_related(
                "subject", "classroom", "teacher", "session", "term"
            ).get(id=classroom_subject_id)
        except ObjectDoesNotExist:
            raise serializers.ValidationError({
                "classroom_subject_id": "Invalid teaching assignment."
            }) from None

        # Validate assessment type
        try:
            assessment_type = AssessmentType.objects.get(id=assessment_type_id)
        except ObjectDoesNotExist:
            raise serializers.ValidationError({
                "assessment_type_id": "Invalid assessment type."
            }) from None

        # Validate index
        if index < 1 or index > assessment_type.max_assessments:
            raise serializers.ValidationError({
                "index": f"Index must be between 1 and {assessment_type.max_assessments}."
            })

        # Validate all students are enrolled in the subject for session & term
        student_ids = [entry["student_id"] for entry in entries]
        enrolled_students = StudentSubjectEnrollment.objects.filter(
            student_id__in=student_ids,
            subject=classroom_subject.subject,
            session=classroom_subject.session,
            term=classroom_subject.term
        ).values_list("student_id", flat=True)

        invalid_students = set(student_ids) - set(enrolled_students)
        if invalid_students:
            raise serializers.ValidationError({
                "entries": f"Students {list(invalid_students)} are not enrolled in this subject for this session/term."
            })

        # Attach objects for create()
        data["classroom_subject"] = classroom_subject
        data["assessment_type"] = assessment_type
        return data

    @transaction.atomic
    def create(self, validated_data):
        classroom_subject = validated_data["classroom_subject"]
        assessment_type = validated_data["assessment_type"]
        index = validated_data["index"]

        records = []
        for entry in validated_data["entries"]:
            student = StudentProfile.objects.get(id=entry["student_id"])
            score = entry["score"]
            percentage_score = float(Decimal(score) / Decimal(assessment_type.max_score) * 100)

            record, _ = AssessmentRecord.objects.update_or_create(
                student=student,
                classroom_subject=classroom_subject,
                assessment_type=assessment_type,
                index=index,
                defaults={"score": score, "percentage_score": percentage_score}
            )
            records.append(record)

        return {
            "message": f"{len(records)} assessment records processed successfully.",
            "records": AssessmentRecordSerializer(records, many=True).data,
            "count": len(records),
        }
