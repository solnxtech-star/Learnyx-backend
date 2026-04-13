from core.applications.grading.models import SubjectResult
from rest_framework import serializers

from core.applications.academics.models import AcademicTerm, AssessmentRecord, ClassRoom

# serializers.py

class AssessmentRecordReviewSerializer(serializers.ModelSerializer):
    """
    What the admin sees per record in the review list.
    """
    student_name    = serializers.CharField(source="student.user.name", read_only=True)
    student_id_no   = serializers.CharField(source="student.student_id", read_only=True)
    subject_name    = serializers.CharField(source="classroom_subject.name", read_only=True)
    assessment_name = serializers.CharField(source="assessment_type.name", read_only=True)
    category        = serializers.CharField(source="assessment_type.category", read_only=True)
    max_score       = serializers.FloatField(source="assessment_type.max_score", read_only=True)
    period_name     = serializers.CharField(source="period.name", read_only=True)

    class Meta:
        model  = AssessmentRecord
        fields = [
            "id",
            "student_name",
            "student_id_no",
            "subject_name",
            "assessment_name",
            "category",
            "score",
            "max_score",
            "index",
            "date_taken",
            "period_name",
            "status",
            "remarks",
            "created_at",
        ]

class ReviewActionSerializer(serializers.Serializer):
    """Single record approve/reject."""
    action  = serializers.ChoiceField(choices=["approve", "reject"])
    remarks = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, data):
        if data["action"] == "reject" and not data.get("remarks", "").strip():
            raise serializers.ValidationError(
                {"remarks": "Remarks are required when rejecting a record."}
            )
        return data


class BulkReviewActionSerializer(serializers.Serializer):
    """Bulk approve/reject."""
    record_ids = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
    )
    action  = serializers.ChoiceField(choices=["approve", "reject"])
    remarks = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, data):
        if data["action"] == "reject" and not data.get("remarks", "").strip():
            raise serializers.ValidationError(
                {"remarks": "Remarks are required when rejecting records."}
            )
        return data


class ComputeResultsSerializer(serializers.Serializer):
    """
    Admin explicitly triggers result computation for a class and term.
    Stage is required — admin decides whether this is a half-term
    or end-of-term computation.
    """
    classroom_id = serializers.PrimaryKeyRelatedField(
        queryset=ClassRoom.objects.all(), source="classroom"
    )
    term_id = serializers.PrimaryKeyRelatedField(
        queryset=AcademicTerm.objects.all(), source="term"
    )
    stage = serializers.ChoiceField(
        choices=SubjectResult.Stage.choices,
        help_text="HALF_TERM or END_OF_TERM — admin decides explicitly."
    )


class PublishResultsSerializer(serializers.Serializer):
    """
    Admin explicitly publishes computed results for a class, term, and stage.
    Only computed (unpublished) results can be published.
    """
    classroom_id = serializers.PrimaryKeyRelatedField(
        queryset=ClassRoom.objects.all(), source="classroom"
    )
    term_id = serializers.PrimaryKeyRelatedField(
        queryset=AcademicTerm.objects.all(), source="term"
    )
    stage = serializers.ChoiceField(choices=SubjectResult.Stage.choices)


class SubjectResultSerializer(serializers.ModelSerializer):
    """What admin sees after computation before publishing."""
    student_name   = serializers.CharField(source="student.user.name", read_only=True)
    student_id_no  = serializers.CharField(source="student.student_id", read_only=True)
    subject_name   = serializers.CharField(source="classroom_subject.name", read_only=True)

    class Meta:
        model  = SubjectResult
        fields = [
            "id",
            "student_name",
            "student_id_no",
            "subject_name",
            "stage",
            "total_ca",
            "exam_score",
            "half_term_score",
            "total_score",
            "average_score",
            "grade",
            "grade_point",
            "comment",
            "is_published",
            "created_at",
            "updated_at",
        ]
