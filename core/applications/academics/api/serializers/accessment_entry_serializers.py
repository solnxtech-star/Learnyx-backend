from django.db import transaction
from rest_framework import serializers

from core.applications.academics.models import AssessmentRecord


class AssessmentRecordSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and managing individual assessment records.

    This serializer:
    - Ensures students, subjects, and classes belong to the same school.
    - Validates that the student belongs to the classroom of the teaching assignment.
    - Validates assessment index limits based on the assessment type.
    - Validates score ranges (must not exceed assessment_type.max_score).
    - Automatically calculates `percentage_score` during creation.
    - Exposes read-only contextual fields such as student name, subject name, and assessment type name.

    Expected Input:
        {
            "student": <student_id>,
            "classroom_subject": <teaching_assignment_id>,
            "assessment_type": <assessment_type_id>,
            "index": 1,
            "score": 15
        }

    Notes:
        - `classroom_subject` MUST be a TeachingAssignment ID.
        - `percentage_score` is calculated as: (score / max_score) * 100.
    """

    student_name = serializers.CharField(source="student.user.name", read_only=True)
    student_id = serializers.CharField(source="student.student_id", read_only=True)

    subject_name = serializers.CharField(
        source="classroom_subject.subject.name",
        read_only=True
    )

    assessment_type_name = serializers.CharField(
        source="assessment_type.name",
        read_only=True
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
        """
        Perform multi-step validation on assessment data.

        Validation includes:
        1. Ensuring classroom_subject is a valid TeachingAssignment instance.
        2. Multi-tenancy checks — student, class, subject must belong to the same school.
        3. Ensuring the student belongs to the classroom assigned to the teacher.
        4. Ensuring `index` does not exceed the allowed number of assessments.
        5. Ensuring `score` does not exceed the max score allowed for the assessment type.
        """
        ...
        return data

    def create(self, validated_data):
        """
        Create an assessment record and auto-calculate `percentage_score`.

        Computation:
            percentage_score = (score / assessment_type.max_score) * 100
        """
        ...
        return super().create(validated_data)


class AssessmentEntryFormDataSerializer(serializers.Serializer):
    """
    Serializer for validating classroom and subject selection when loading
    assessment entry forms.

    Responsibilities:
    - Ensures the classroom exists and belongs to the requesting user's school.
    - Ensures the subject exists, belongs to the same school, and is active.
    - Adds the validated `class_room` and `subject` objects to the returned data.

    Expected Input:
        {
            "class_room_id": 5,
            "subject_id": 10
        }
    """

    class_room_id = serializers.IntegerField()
    subject_id = serializers.IntegerField()

    def validate(self, data):
        """
        Validate that the classroom and subject belong to the user's school.
        """
        ...
        return data

class StudentScoreEntrySerializer(serializers.Serializer):
    """
    Serializer representing a single student's score entry for bulk assessment upload.

    Fields:
        - student_id: The ID of the student.
        - score: The score assigned to the student (must be >= 0).

    Used inside:
        BulkAssessmentEntrySerializer.entries
    """

    student_id = serializers.IntegerField()
    score = serializers.FloatField(min_value=0)

    def validate(self, data):
        """
        Ensure score is non-negative.
        """
        if data["score"] < 0:
            raise serializers.ValidationError({"score": "Score cannot be negative"})
        return data



class BulkAssessmentEntrySerializer(serializers.Serializer):
    """
    Serializer for bulk creation or update of assessment records.

    Handles multiple students' scores for a single:
    - teaching assignment (`classroom_subject`)
    - assessment type
    - index

    Responsibilities:
    - Validates teaching assignment belongs to the user's school.
    - Validates assessment type belongs to the user's school.
    - Ensures `index` does not exceed allowed assessment count.
    - Ensures all submitted student IDs belong to the classroom.
    - Creates or updates AssessmentRecord objects in bulk.
    - Computes and stores `percentage_score` for each created record.

    Expected Input:
        {
            "classroom_subject_id": 10,
            "assessment_type_id": 4,
            "index": 2,
            "entries": [
                {"student_id": 12, "score": 18},
                {"student_id": 14, "score": 20}
            ]
        }
    """

    classroom_subject_id = serializers.IntegerField()
    assessment_type_id = serializers.IntegerField()
    index = serializers.IntegerField(min_value=1)

    entries = serializers.ListField(
        child=StudentScoreEntrySerializer(),
        min_length=1,
    )

    def validate(self, data):
        """
        Validate:
        - classroom_subject exists and belongs to the requesting user's school.
        - assessment_type exists and belongs to the requesting user's school.
        - index is within allowed range.
        - all students belong to the classroom given by classroom_subject.
        """
        ...
        return data

    @transaction.atomic
    def create(self, validated_data):
        """
        Bulk create or update assessment records for all students.

        For each student:
            - update_or_create AssessmentRecord
            - compute (score / max_score) * 100
            - save percentage_score

        Returns:
            {
                "message": "...",
                "records": [...serialized records...],
                "count": <number_of_records>
            }
        """
        ...
        return {...}
