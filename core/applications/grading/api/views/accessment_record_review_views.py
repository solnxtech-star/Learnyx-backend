import logging

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from core.applications.grading.models import SubjectResult
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.applications.academics.models import AssessmentRecord
from core.applications.academics.services.student_class_service import (
    get_student_active_classroom,
)
from core.applications.academics.services.student_class_service import (
    get_term_from_assessment,
)
from core.applications.grading.api.schemas import result_schema
from core.applications.grading.api.serializers.accessment_record_review_serializers import (
    AssessmentRecordReviewSerializer,
    ComputeResultsSerializer,
    PublishResultsSerializer,
    SubjectResultSerializer,
)
from core.applications.grading.api.serializers.accessment_record_review_serializers import (
    BulkReviewActionSerializer,
)
from core.applications.grading.api.serializers.accessment_record_review_serializers import (
    ReviewActionSerializer,
)
from core.helper.enums import ReviewStatus
from core.helper.permissions import IsPrincipalOrSchoolOwner
from core.helper.service import compute_all_subject_results
from core.helper.service import compute_term_summary

logger = logging.getLogger(__name__)

@result_schema
class AssessmentReviewViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    """
    Admin-only review and result management workflow.

    Endpoints:
      GET    /assessments/review/                         → list records
      GET    /assessments/review/summary/                 → status counts
      POST   /assessments/review/{id}/action/             → approve or reject one record
      POST   /assessments/review/bulk-action/             → approve or reject many records
      POST   /assessments/review/compute-results/         → explicitly compute results
      POST   /assessments/review/publish-results/         → explicitly publish results
      GET    /assessments/review/computed-results/        → view computed results before publishing
    """
    serializer_class   = AssessmentRecordReviewSerializer
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]

    def get_queryset(self):
        params       = self.request.query_params
        status_val   = params.get("status", ReviewStatus.PENDING)
        subject_id   = params.get("subject_id")
        classroom_id = params.get("classroom_id")
        term_id      = params.get("term_id")

        qs = (
            AssessmentRecord.objects
            .select_related(
                "student__user",
                "classroom_subject",
                "assessment_type",
                "period",
            )
            .filter(status=status_val)
            .order_by("-created_at")
        )

        if subject_id:
            qs = qs.filter(classroom_subject_id=subject_id)
        if classroom_id:
            qs = qs.filter(classroom_subject__class_rooms=classroom_id)
        if term_id:
            qs = qs.filter(period__term_id=term_id)  # filter via period → term

        return qs

    # ------------------------------------------------------------------
    # GET /assessments/review/summary/
    # ------------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        base_qs      = AssessmentRecord.objects.all()
        subject_id   = request.query_params.get("subject_id")
        classroom_id = request.query_params.get("classroom_id")
        term_id      = request.query_params.get("term_id")

        if subject_id:
            base_qs = base_qs.filter(classroom_subject_id=subject_id)
        if classroom_id:
            base_qs = base_qs.filter(classroom_subject__class_rooms=classroom_id)
        if term_id:
            base_qs = base_qs.filter(period__term_id=term_id)

        counts = base_qs.values("status").annotate(count=Count("id"))
        result = {row["status"]: row["count"] for row in counts}

        return Response({
            "pending":  result.get(ReviewStatus.PENDING, 0),
            "approved": result.get(ReviewStatus.APPROVED, 0),
            "rejected": result.get(ReviewStatus.REJECTED, 0),
        })

    # ------------------------------------------------------------------
    # POST /assessments/review/{id}/action/
    # ------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="action")
    @transaction.atomic
    def review_action(self, request, pk=None):
        record = get_object_or_404(
            AssessmentRecord.objects.select_related(
                "student", "classroom_subject", "assessment_type", "period"
            ),
            pk=pk,
        )

        if record.status == ReviewStatus.APPROVED:
            raise ValidationError({
                "detail": "This record has already been approved and cannot be changed."
            })

        serializer = ReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action_val = serializer.validated_data["action"]
        remarks    = serializer.validated_data.get("remarks", "")

        if action_val == "approve":
            record.status  = ReviewStatus.APPROVED
            record.remarks = ""
        else:
            record.status  = ReviewStatus.REJECTED
            record.remarks = remarks

        record.save(update_fields=["status", "remarks", "updated_at"])

        logger.info(
            "[REVIEW] Record id=%s set to status=%s", record.id, record.status
        )

        # No recomputation here — admin triggers that explicitly
        return Response(
            AssessmentRecordReviewSerializer(record).data,
            status=status.HTTP_200_OK,
        )

    # ------------------------------------------------------------------
    # POST /assessments/review/bulk-action/
    # ------------------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="bulk-action")
    @transaction.atomic
    def bulk_review_action(self, request):
        serializer = BulkReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record_ids = serializer.validated_data["record_ids"]
        action_val = serializer.validated_data["action"]
        remarks    = serializer.validated_data.get("remarks", "")

        # Snapshot records BEFORE update so we have the objects in memory
        records = list(
            AssessmentRecord.objects.filter(
                id__in=record_ids,
                status__in=[ReviewStatus.PENDING, ReviewStatus.REJECTED],
            ).select_related("student", "classroom_subject", "assessment_type", "period")
        )

        found_ids   = [r.id for r in records]
        skipped_ids = list(set(record_ids) - set(found_ids))

        new_status = (
            ReviewStatus.APPROVED if action_val == "approve"
            else ReviewStatus.REJECTED
        )

        # Bulk update status
        update_kwargs = {"status": new_status}
        if action_val == "reject":
            update_kwargs["remarks"] = remarks

        AssessmentRecord.objects.filter(id__in=found_ids).update(**update_kwargs)

        logger.info(
            "[BULK] %s %d records — skipped %d",
            action_val, len(found_ids), len(skipped_ids)
        )

        # No recomputation here — admin triggers that explicitly
        return Response({
            "action":        action_val,
            "updated_count": len(found_ids),
            "skipped_ids":   skipped_ids,
        }, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # POST /assessments/review/compute-results/
    # Admin explicitly computes results for a classroom + term + stage.
    # This never auto-publishes — admin reviews first.
    # ------------------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="compute-results")
    @transaction.atomic
    def compute_results(self, request):
        serializer = ComputeResultsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        classroom = serializer.validated_data["classroom"]
        term      = serializer.validated_data["term"]
        stage     = serializer.validated_data["stage"]

        logger.info(
            "[COMPUTE] Admin triggered computation — classroom=%s term=%s stage=%s",
            classroom.id, term.id, stage
        )

        result = compute_all_subject_results(classroom, term, stage)
        compute_term_summary(classroom, term, stage)

        logger.info(
            "[COMPUTE] Done — created=%s updated=%s",
            result["created"], result["updated"]
        )

        return Response({
            "detail":  f"Results computed successfully for stage '{stage}'.",
            "created": result["created"],
            "updated": result["updated"],
        }, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # GET /assessments/review/computed-results/
    # Admin previews computed results before deciding to publish.
    # ------------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="computed-results")
    def computed_results(self, request):
        classroom_id = request.query_params.get("classroom_id")
        term_id      = request.query_params.get("term_id")
        stage        = request.query_params.get("stage")

        if not all([classroom_id, term_id, stage]):
            raise ValidationError({
                "detail": "classroom_id, term_id, and stage are required."
            })

        results = (
            SubjectResult.objects
            .select_related("student__user", "classroom_subject")
            .filter(
                classroom_subject__class_rooms=classroom_id,
                term_id=term_id,
                stage=stage,
            )
            .order_by("student__user__name", "classroom_subject__name")
        )

        return Response(
            SubjectResultSerializer(results, many=True).data,
            status=status.HTTP_200_OK,
        )

    # ------------------------------------------------------------------
    # POST /assessments/review/publish-results/
    # Admin explicitly publishes computed results.
    # Only unpublished results are affected.
    # Published results are immutable — cannot be unpublished here.
    # ------------------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="publish-results")
    @transaction.atomic
    def publish_results(self, request):
        serializer = PublishResultsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        classroom = serializer.validated_data["classroom"]
        term      = serializer.validated_data["term"]
        stage     = serializer.validated_data["stage"]

        results = SubjectResult.objects.filter(
            classroom_subject__class_rooms=classroom,
            term=term,
            stage=stage,
            is_published=False,  # only unpublished results
        )

        count = results.count()

        if not count:
            raise ValidationError({
                "detail": (
                    f"No unpublished results found for stage '{stage}'. "
                    "Ensure results have been computed first."
                )
            })

        results.update(is_published=True)

        logger.info(
            "[PUBLISH] Admin published %d results — classroom=%s term=%s stage=%s",
            count, classroom.id, term.id, stage
        )

        return Response({
            "detail":           f"{count} results published successfully.",
            "published_count":  count,
            "stage":            stage,
        }, status=status.HTTP_200_OK)
