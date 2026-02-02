from django.db import models
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import filters
from rest_framework import serializers
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.applications.academics.models import AssessmentPolicy
from core.applications.academics.models import AssessmentType
from core.applications.users.api.schemas import ActivePolicyForTermSchema
from core.applications.users.api.schemas import ApplyDefaultPolicySchema
from core.applications.users.api.schemas import AssessmentPolicySchema
from core.applications.users.api.schemas import AssessmentTypeSchema
from core.applications.users.api.serializers.admin_accessment_serializers import (
    AssessmentPolicyCreateSerializer,
)
from core.applications.users.api.serializers.admin_accessment_serializers import (
    AssessmentPolicyListSerializer,
)

# from core.applications.users.api.serializers.admin_accessment_serializers import (
#     AssessmentPolicySerializer,
# )
from core.applications.users.api.serializers.admin_accessment_serializers import (
    AssessmentPolicyUpdateSerializer,
)
from core.applications.users.api.serializers.admin_accessment_serializers import (
    AssessmentTypeSerializer,
)
from core.applications.users.api.serializers.admin_accessment_serializers import (
    DefaultAssessmentPolicySerializer,
)
from core.helper.permissions import IsPrincipalOrSchoolOwnerForPolicies


@extend_schema(tags=["AccessmentPolicy"])
@AssessmentPolicySchema
class AssessmentPolicyViewSet(viewsets.ModelViewSet):
    """
    Assessment Policy API.

    Responsibilities:
    - List and retrieve assessment policies for a school
    - Create policies with strict business rules
    - Edit policies safely without breaking uniqueness constraints
    - Apply predefined default policies
    - Fetch active policy/policies for a term
    """

    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwnerForPolicies]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ["created_at", "name", "term"]
    search_fields = ["name", "term__name"]

    # -----------------------------
    # Queryset scoping
    # -----------------------------
    def get_queryset(self):
        """
        Scope all operations strictly to the user's school.
        """
        return (
            AssessmentPolicy.objects
            .filter(school=self.request.user.school)
            .select_related("school", "term")
        )

    # -----------------------------
    # Serializer selection
    # -----------------------------
    def get_serializer_class(self):
        """
        Use explicit serializers per action.
        """
        if self.action == "create":
            return AssessmentPolicyCreateSerializer
        if self.action in ("update", "partial_update"):
            return AssessmentPolicyUpdateSerializer
        return AssessmentPolicyListSerializer

    # -----------------------------
    # Create hook
    # -----------------------------
    def perform_create(self, serializer):
        """
        School is always derived from the authenticated user.
        """
        serializer.save(school=self.request.user.school)

    # -----------------------------
    # Custom actions
    # -----------------------------
    @ApplyDefaultPolicySchema
    @action(
        detail=False,
        methods=["post"],
        url_path="apply-default",
    )
    @transaction.atomic
    def apply_default(self, request):
        """
        Apply a predefined default assessment policy to a term.

        - Deactivates any existing active policy for the term
        - Creates assessment types automatically
        """
        serializer = DefaultAssessmentPolicySerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        policy = serializer.save()

        return Response(
            {
                "message": "Default assessment policy created successfully.",
                "policy": AssessmentPolicyListSerializer(
                    policy, context={"request": request}
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @ActivePolicyForTermSchema
    @action(
        detail=False,
        methods=["get"],
        url_path="active-for-term",
    )
    def active_for_term(self, request):
        """
        Retrieve active assessment policy/policies.

        - If `term` query param is provided → return single active policy
        - If omitted → return all active policies for the school
        """
        school = request.user.school
        term_id = request.query_params.get("term")

        queryset = AssessmentPolicy.objects.filter(
            school=school,
            is_active=True,
        ).select_related("term", "school")

        if term_id:
            policy = queryset.filter(term_id=term_id).first()

            if not policy:
                return Response(
                    {"detail": "No active assessment policy found for this term."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(
                AssessmentPolicyListSerializer(
                    policy, context={"request": request}
                ).data,
                status=status.HTTP_200_OK,
            )

        return Response(
            AssessmentPolicyListSerializer(
                queryset, many=True, context={"request": request}
            ).data,
            status=status.HTTP_200_OK,
        )


# -------------------------------------------------------
# Assessment Type ViewSet
# -------------------------------------------------------

@extend_schema(tags=["AccessmentType"])
@AssessmentTypeSchema
class AssessmentTypeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing AssessmentType instances.

    Validations:
        - Policy must belong to the user's school.
        - Default policies cannot exceed 100% total weight.
        - Auto-assign order if not provided.
    """
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwnerForPolicies]
    serializer_class = AssessmentTypeSerializer
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ["order", "name", "created_at"]
    search_fields = ["name", "category"]

    def get_queryset(self):
        user = self.request.user
        qs = AssessmentType.objects.filter(
            policy__school=user.school
        ).select_related("policy")

        policy_id = self.request.query_params.get("policy")
        if policy_id:
            qs = qs.filter(policy_id=policy_id)
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        policy = serializer.validated_data.get("policy")
        user = self.request.user

        # -----------------------------
        # School ownership check
        # -----------------------------
        if policy.school != user.school:
            raise serializers.ValidationError({
                "policy": _("Selected policy does not belong to your school.")
            })

        # -----------------------------
        # Default policy total weight check
        # -----------------------------
        if getattr(policy, "is_default", False):
            total_weight = policy.assessment_types.aggregate(
                total=models.Sum("weight")
            )["total"] or 0

            new_weight = serializer.validated_data.get("weight", 0)
            if total_weight + new_weight > 100:
                raise serializers.ValidationError({
                    "weight": _(
                        "Cannot add new type: default policy already has 100% total weight. "
                        "Current total: %(current)d%%, Trying to add: %(adding)d%%"
                    ) % {"current": total_weight, "adding": new_weight}
                })

        # -----------------------------
        # Auto-assign order
        # -----------------------------
        if "order" not in serializer.validated_data:
            last_order = policy.assessment_types.aggregate(
                max_order=models.Max("order")
            )["max_order"] or 0
            serializer.validated_data["order"] = last_order + 1

        serializer.save()

    @transaction.atomic
    def perform_update(self, serializer):
        instance = serializer.instance
        policy = serializer.validated_data.get("policy", instance.policy)
        user = self.request.user

        # -----------------------------
        # School ownership check
        # -----------------------------
        if policy.school != user.school:
            raise serializers.ValidationError({
                "policy": _("Selected policy does not belong to your school.")
            })

        # -----------------------------
        # Default policy weight check
        # -----------------------------
        if getattr(policy, "is_default", False):
            total_weight = policy.assessment_types.exclude(
                id=instance.id
            ).aggregate(total=models.Sum("weight"))["total"] or 0

            new_weight = serializer.validated_data.get("weight", instance.weight)
            if total_weight + new_weight > 100:
                raise serializers.ValidationError({
                    "weight": _(
                        "Cannot update type: default policy weight would exceed 100%. "
                        "Current total (excluding this type): %(current)d%%, Trying to set: %(adding)d%%"
                    ) % {"current": total_weight, "adding": new_weight}
                })

        serializer.save()
