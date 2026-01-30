from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import filters
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
    AssessmentPolicySerializer,
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
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwnerForPolicies]
    serializer_class = AssessmentPolicySerializer
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ["created_at", "name", "term"]
    search_fields = ["name", "term__name"]

    def get_queryset(self):
        user = self.request.user
        return AssessmentPolicy.objects.filter(
            school=user.school
        ).select_related("term", "school")

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)

    def perform_update(self, serializer):
        serializer.save(school=self.request.user.school)

    @ApplyDefaultPolicySchema
    @action(detail=False, methods=["post"], url_path="apply-default")
    @transaction.atomic
    def apply_default(self, request):
        serializer = DefaultAssessmentPolicySerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        policy = serializer.create(serializer.validated_data)
        output = AssessmentPolicySerializer(policy, context={"request": request}).data

        return Response(
            {"message": "Default policy created", "policy": output},
            status=status.HTTP_201_CREATED
        )

    @ActivePolicyForTermSchema
    @action(detail=False, methods=["get"], url_path="active-for-term")
    def active_for_term(self, request):
        term_id = request.query_params.get("term")
        school = request.user.school

        if term_id:
            policy = AssessmentPolicy.objects.filter(
                school=school, term_id=term_id, is_active=True
            ).first()

            if not policy:
                return Response(
                    {"detail": "No active policy for the provided term."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(
                AssessmentPolicySerializer(policy, context={"request": request}).data
            )

        policies = AssessmentPolicy.objects.filter(school=school, is_active=True)
        return Response(
            AssessmentPolicySerializer(policies, many=True, context={"request": request}).data
        )


# -------------------------------------------------------
# Assessment Type ViewSet
# -------------------------------------------------------

@extend_schema(tags=["AccessmentType"])
@AssessmentTypeSchema
class AssessmentTypeViewSet(viewsets.ModelViewSet):
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

    def perform_create(self, serializer):
        policy = serializer.validated_data.get("policy")

        if policy.school != self.request.user.school:
            raise ValueError("Policy does not belong to your school.")

        serializer.save()

    def perform_update(self, serializer):
        policy = serializer.validated_data.get("policy", serializer.instance.policy)

        if policy.school != self.request.user.school:
            raise ValueError("Policy does not belong to your school.")

        serializer.save()
