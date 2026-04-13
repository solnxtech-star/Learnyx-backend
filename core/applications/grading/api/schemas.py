from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from drf_spectacular.utils import inline_serializer
from rest_framework import serializers as drf_serializers

from core.applications.grading.api.serializers.accessment_record_review_serializers import (
    AssessmentRecordReviewSerializer,
)
from core.applications.grading.api.serializers.accessment_record_review_serializers import (
    BulkReviewActionSerializer,
)
from core.applications.grading.api.serializers.accessment_record_review_serializers import (
    ComputeResultsSerializer,
)
from core.applications.grading.api.serializers.accessment_record_review_serializers import (
    PublishResultsSerializer,
)
from core.applications.grading.api.serializers.accessment_record_review_serializers import (
    ReviewActionSerializer,
)
from core.applications.grading.api.serializers.accessment_record_review_serializers import (
    SubjectResultSerializer,
)

REVIEW_FILTER_PARAMETERS = [
    OpenApiParameter(
        name="subject_id",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by subject UUID.",
    ),
    OpenApiParameter(
        name="classroom_id",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by classroom UUID.",
    ),
    OpenApiParameter(
        name="term_id",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by term UUID. Resolved via period → term.",
    ),
]

result_schema = extend_schema_view(

    # ------------------------------------------------------------------
    # GET /assessments/review/
    # ------------------------------------------------------------------
    list=extend_schema(
        tags=["Admin Management"],
        summary="List assessment records for review",
        description=(
            "Returns a paginated list of assessment records filtered by status. "
            "Defaults to `pending` if no status is provided. "
            "Only accessible by principals and school owners."
        ),
        parameters=[
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                default="pending",
                enum=["pending", "approved", "rejected"],
                description="Filter records by review status. Defaults to `pending`.",
            ),
            *REVIEW_FILTER_PARAMETERS,
        ],
        responses={
            200: AssessmentRecordReviewSerializer(many=True),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            403: OpenApiResponse(description="You do not have permission to perform this action."),
        },
    ),

    # ------------------------------------------------------------------
    # GET /assessments/review/summary/
    # ------------------------------------------------------------------
    summary=extend_schema(
        tags=["Admin Management"],
        summary="Get review status summary counts",
        description=(
            "Returns the count of assessment records grouped by review status "
            "(pending, approved, rejected). Used to drive the dashboard stat cards. "
            "Supports the same subject/classroom/term filters as the list endpoint."
        ),
        parameters=REVIEW_FILTER_PARAMETERS,
        responses={
            200: OpenApiResponse(
                description="Status counts returned successfully.",
                response=inline_serializer(
                    name="ReviewSummaryResponse",
                    fields={
                        "pending":  drf_serializers.IntegerField(),
                        "approved": drf_serializers.IntegerField(),
                        "rejected": drf_serializers.IntegerField(),
                    },
                ),
            ),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            403: OpenApiResponse(description="You do not have permission to perform this action."),
        },
    ),

    # ------------------------------------------------------------------
    # POST /assessments/review/{id}/action/
    # ------------------------------------------------------------------
    review_action=extend_schema(
        tags=["Admin Management"],
        summary="Approve or reject a single assessment record",
        description=(
            "Approves or rejects a single assessment record by ID. "
            "Already-approved records cannot be changed — a 400 is returned if attempted. "
            "Rejections require a `remarks` field explaining the reason. "
            "\n\n"
            "**Note:** Approving a record does NOT trigger result computation. "
            "Results are computed separately via `POST /compute-results/` "
            "once the admin is satisfied all records are approved."
        ),
        request=ReviewActionSerializer,
        responses={
            200: AssessmentRecordReviewSerializer,
            400: OpenApiResponse(
                description=(
                    "Validation error. Possible causes:\n"
                    "- `remarks` missing when action is `reject`\n"
                    "- Record is already approved"
                )
            ),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            403: OpenApiResponse(description="You do not have permission to perform this action."),
            404: OpenApiResponse(description="Assessment record not found."),
        },
    ),

    # ------------------------------------------------------------------
    # POST /assessments/review/bulk-action/
    # ------------------------------------------------------------------
    bulk_review_action=extend_schema(
        tags=["Admin Management"],
        summary="Approve or reject multiple assessment records",
        description=(
            "Bulk approves or rejects a list of assessment records by their IDs. "
            "Records that are already approved are automatically skipped and returned in `skipped_ids`. "
            "Only `pending` and `rejected` records are affected. "
            "Rejections require a `remarks` field. "
            "\n\n"
            "**Note:** Approving records does NOT trigger result computation. "
            "Results are computed separately via `POST /compute-results/` "
            "once the admin is satisfied all records are approved."
        ),
        request=BulkReviewActionSerializer,
        responses={
            200: OpenApiResponse(
                description="Bulk action completed. Returns counts of updated and skipped records.",
                response=inline_serializer(
                    name="BulkReviewActionResponse",
                    fields={
                        "action":        drf_serializers.ChoiceField(choices=["approve", "reject"]),
                        "updated_count": drf_serializers.IntegerField(),
                        "skipped_ids":   drf_serializers.ListField(
                            child=drf_serializers.CharField()
                        ),
                    },
                ),
            ),
            400: OpenApiResponse(
                description=(
                    "Validation error. Possible causes:\n"
                    "- `record_ids` is empty\n"
                    "- `remarks` missing when action is `reject`"
                )
            ),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            403: OpenApiResponse(description="You do not have permission to perform this action."),
        },
    ),

    # ------------------------------------------------------------------
    # POST /assessments/review/compute-results/
    # ------------------------------------------------------------------
    compute_results=extend_schema(
        tags=["Admin Management"],
        summary="Compute results for a class and term",
        description=(
            "Admin explicitly triggers result computation for a specific classroom, "
            "term, and stage. \n\n"
            "This aggregates all **approved** assessment scores across all periods "
            "within the term, applies the school's CA/Exam weighting policy, "
            "assigns grades, and saves results privately. \n\n"
            "**Students cannot see results at this point** — results are saved "
            "with `is_published=False` until the admin explicitly publishes them. \n\n"
            "Calling this endpoint again after more records are approved simply "
            "updates existing unpublished results — it never duplicates or "
            "overwrites published results. \n\n"
            "**Stage guidance:** \n"
            "- `HALF_TERM` — computes CA scores only, no grade assigned. "
            "Use at mid-term checkpoint. \n"
            "- `END_OF_TERM` — computes CA + Exam, assigns grades. "
            "Use at end of term."
        ),
        request=ComputeResultsSerializer,
        responses={
            200: OpenApiResponse(
                description="Results computed successfully.",
                response=inline_serializer(
                    name="ComputeResultsResponse",
                    fields={
                        "detail":  drf_serializers.CharField(),
                        "created": drf_serializers.IntegerField(),
                        "updated": drf_serializers.IntegerField(),
                    },
                ),
            ),
            400: OpenApiResponse(
                description=(
                    "Validation error. Possible causes:\n"
                    "- `classroom_id` not found\n"
                    "- `term_id` not found\n"
                    "- `stage` is not a valid choice"
                )
            ),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            403: OpenApiResponse(description="You do not have permission to perform this action."),
        },
    ),

    # ------------------------------------------------------------------
    # GET /assessments/review/computed-results/
    # ------------------------------------------------------------------
    computed_results=extend_schema(
        tags=["Admin Management"],
        summary="Preview computed results before publishing",
        description=(
            "Returns all computed but unpublished subject results for a given "
            "classroom, term, and stage. \n\n"
            "Admin uses this to review every student's grade and score "
            "before deciding to publish. Students cannot see these results yet. \n\n"
            "All three query parameters are required."
        ),
        parameters=[
            OpenApiParameter(
                name="classroom_id",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="UUID of the classroom to preview results for.",
            ),
            OpenApiParameter(
                name="term_id",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="UUID of the term to preview results for.",
            ),
            OpenApiParameter(
                name="stage",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                enum=["HALF_TERM", "END_OF_TERM"],
                description="The computation stage to preview.",
            ),
        ],
        responses={
            200: SubjectResultSerializer(many=True),
            400: OpenApiResponse(
                description="classroom_id, term_id, and stage are all required."
            ),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            403: OpenApiResponse(description="You do not have permission to perform this action."),
        },
    ),

    # ------------------------------------------------------------------
    # POST /assessments/review/publish-results/
    # ------------------------------------------------------------------
    publish_results=extend_schema(
        tags=["Admin Management"],
        summary="Publish computed results to students",
        description=(
            "Publishes all computed results for a classroom, term, and stage, "
            "making them visible to students and parents. \n\n"
            "**This action is irreversible** — once published, results cannot "
            "be unpublished. Only results with `is_published=False` are affected; "
            "already-published results are never touched. \n\n"
            "A 400 is returned if no unpublished results are found — "
            "this typically means `POST /compute-results/` has not been called yet."
        ),
        request=PublishResultsSerializer,
        responses={
            200: OpenApiResponse(
                description="Results published successfully.",
                response=inline_serializer(
                    name="PublishResultsResponse",
                    fields={
                        "detail":          drf_serializers.CharField(),
                        "published_count": drf_serializers.IntegerField(),
                        "stage":           drf_serializers.CharField(),
                    },
                ),
            ),
            400: OpenApiResponse(
                description=(
                    "Validation error. Possible causes:\n"
                    "- No unpublished results found for the given classroom/term/stage\n"
                    "- `compute-results` has not been called yet"
                )
            ),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            403: OpenApiResponse(description="You do not have permission to perform this action."),
        },
    ),
)
