from django.db import IntegrityError
from django.db import models
from django.db import transaction
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import AssessmentPolicy
from core.applications.academics.models import AssessmentType


class AssessmentTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for the AssessmentType model.

    Handles professional validation for:
    - Assessment weights (cannot exceed 100% per policy)
    - Count (must be >= 1)
    - Maximum score (must be positive)
    - Policy ownership (must belong to the user's school)

    Read-only fields:
    - policy_name: Name of the parent AssessmentPolicy
    - category_display: Human-readable category name
    """

    MAX_WEIGHT_PERCENTAGE = 100
    policy_name = serializers.CharField(source="policy.name", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = AssessmentType
        fields = [
            "id",
            "policy",
            "policy_name",
            "name",
            "category",
            "category_display",
            "count",
            "weight",
            "max_score",
            "is_optional",
            "order",
            "created_at",
            "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, data):
        """
        Validates AssessmentType fields.

        Checks:
        1. Policy belongs to the request user's school.
        2. Weight does not cause policy total to exceed 100%.
        3. Count >= 1
        4. Max score > 0
        """

        instance = getattr(self, "instance", None)
        policy = data.get("policy") or (instance.policy if instance else None)
        weight = data.get("weight", getattr(instance, "weight", None))
        count = data.get("count", getattr(instance, "count", None))
        max_score = data.get("max_score", getattr(instance, "max_score", None))
        request = self.context.get("request")

        if not request:
            raise serializers.ValidationError("Request context is required for validation.")

        # -----------------------------
        # Policy ownership check
        # -----------------------------
        if policy and policy.school != request.user.school:
            raise serializers.ValidationError({
                "policy": _("Selected policy does not belong to your school.")
            })

        # -----------------------------
        # Weight validation
        # -----------------------------
        if policy and weight is not None:
            # Total weight of other types in this policy
            total_weight = policy.assessment_types.exclude(
                id=instance.id if instance else None
            ).aggregate(total=models.Sum("weight"))["total"] or 0

            # Default policy full check
            if getattr(policy, "is_default", False) and total_weight >= self.MAX_WEIGHT_PERCENTAGE:
                raise serializers.ValidationError({
                    "weight": _(
                        "This policy is a default policy and already has 100%% total weight. "
                        "Please edit existing assessment types instead of adding a new one."
                    )
                })

            # General check for exceeding 100%
            if total_weight + weight > self.MAX_WEIGHT_PERCENTAGE:
                raise serializers.ValidationError({
                    "weight": _(
                        "Adding this weight would exceed 100%% for the policy. "
                        "Current total: %(current)d%%, Adding: %(adding)d%%"
                    ) % {"current": total_weight, "adding": weight}
                })

            if weight < 0:
                raise serializers.ValidationError({
                    "weight": _("Weight cannot be negative.")
                })

        # -----------------------------
        # Count validation
        # -----------------------------
        if count is not None and count < 1:
            raise serializers.ValidationError({
                "count": _("Count must be at least 1")
            })

        # -----------------------------
        # Max score validation
        # -----------------------------
        if max_score is not None and max_score <= 0:
            raise serializers.ValidationError({
                "max_score": _("Maximum score must be positive")
            })

        return data


class AssessmentPolicyListSerializer(serializers.ModelSerializer):
    """Read-only serializer for listing assessment policies with related info."""
    school_name = serializers.CharField(source="school.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    assessment_types = AssessmentTypeSerializer(many=True, read_only=True)
    total_weight = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentPolicy
        fields = [
            "id",
            "school",
            "school_name",
            "term",
            "term_name",
            "name",
            "is_active",
            "ca_weight",
            "exam_weight",
            "assessment_types",
            "total_weight",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_total_weight(self, obj):
        return obj.assessment_types.aggregate(total=Sum("weight"))["total"] or 0


class AssessmentPolicyCreateSerializer(serializers.ModelSerializer):
    """
    Tenant-aware serializer for creating AssessmentPolicy instances.

    Enforces:
    1. CA + Exam weights sum to 100
    2. Only one active policy per school + term
    3. School is automatically assigned from authenticated user
    """
    class Meta:
        model = AssessmentPolicy
        fields = ["term", "name", "is_active", "ca_weight", "exam_weight"]

    def validate(self, attrs):
        school = self.context["request"].user.school
        term = attrs["term"]
        is_active = attrs.get("is_active", True)

        if attrs["ca_weight"] + attrs["exam_weight"] != 100:
            raise serializers.ValidationError({
                "ca_weight": _("CA weight and Exam weight must sum to 100%"),
                "exam_weight": _("CA weight and Exam weight must sum to 100%"),
            })

        if is_active and AssessmentPolicy.objects.for_school(school).filter(
            term=term, is_active=True
        ).exists():
            raise serializers.ValidationError({
                "is_active": _("An active assessment policy already exists for this term.")
            })

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data["school"] = self.context["request"].user.school
        try:
            return super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError({
                "is_active": _("An active assessment policy already exists for this term.")
            })


class AssessmentPolicyUpdateSerializer(serializers.ModelSerializer):
    """
    Tenant-aware serializer for updating AssessmentPolicy instances.
    Enforces business rules and school-level uniqueness.
    """
    term = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = AssessmentPolicy
        fields = ["name", "is_active", "ca_weight", "exam_weight", "term"]

    def validate(self, attrs):
        instance = self.instance
        school = self.context["request"].user.school

        ca_weight = attrs.get("ca_weight", instance.ca_weight)
        exam_weight = attrs.get("exam_weight", instance.exam_weight)

        if ca_weight + exam_weight != 100:
            raise serializers.ValidationError({
                "ca_weight": _("CA weight and Exam weight must sum to 100%"),
                "exam_weight": _("CA weight and Exam weight must sum to 100%"),
            })

        if attrs.get("is_active") is True and not instance.is_active:
            exists = AssessmentPolicy.objects.for_school(school).filter(
                term=instance.term, is_active=True
            ).exclude(pk=instance.pk).exists()
            if exists:
                raise serializers.ValidationError({
                    "is_active": _("Another active assessment policy already exists for this term.")
                })

        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except IntegrityError:
            raise serializers.ValidationError({
                "is_active": _("Another active assessment policy already exists for this term.")
            })


class DefaultAssessmentPolicySerializer(serializers.Serializer):
    """
    Tenant-aware serializer for creating or resetting default assessment policies.
    Ensures idempotency and school-level isolation.
    """
    CONFIG_CHOICES = [
        ('standard_60_40', _('Standard: Exam 60% + Tests 40%')),
        ('half_term', _('Half Term: CA 50% + Half Term Exam 50%')),
        ('detailed', _('Detailed: Multiple assessment types')),
    ]

    term = serializers.PrimaryKeyRelatedField(queryset=AcademicTerm.objects.all())
    config_type = serializers.ChoiceField(choices=CONFIG_CHOICES, default='standard_60_40')
    policy_name = serializers.CharField(max_length=150, default="Default Assessment Policy")

    def validate(self, data):
        school = self.context['request'].user.school
        term = data['term']
        if term.session.school != school:
            raise serializers.ValidationError({
                'term': _("Selected term does not belong to your school")
            })
        return data

    @transaction.atomic
    def create(self, validated_data):
        school = self.context["request"].user.school
        term = validated_data["term"]
        config_type = validated_data["config_type"]
        policy_name = validated_data["policy_name"]

        # Check for existing active policy
        policy = AssessmentPolicy.objects.for_school(school).filter(
            term=term, is_active=True
        ).first()

        # Default configs
        default_configs = {
            "standard_60_40": {"ca_weight": 40, "exam_weight": 60, "types": [
                {"name": "Test", "category": "CA", "count": 2, "weight": 40, "max_score": 30, "order": 1},
                {"name": "Exam", "category": "EXAM", "count": 1, "weight": 60, "max_score": 60, "order": 2},
            ]},
            "half_term": {"ca_weight": 50, "exam_weight": 50, "types": [
                {"name": "Continuous Assessment", "category": "CA", "count": 1, "weight": 50, "max_score": 100, "order": 1},
                {"name": "Half Term Exam", "category": "HALF_TERM", "count": 1, "weight": 50, "max_score": 100, "order": 2},
            ]},
            "detailed": {"ca_weight": 40, "exam_weight": 60, "types": [
                {"name": "Test", "category": "CA", "count": 2, "weight": 30, "max_score": 20, "order": 1},
                {"name": "Assignment", "category": "CA", "count": 2, "weight": 10, "max_score": 10, "order": 2},
                {"name": "Exam", "category": "EXAM", "count": 1, "weight": 60, "max_score": 60, "order": 3},
            ]}
        }

        config = default_configs[config_type]

        if policy:
            # Update existing policy
            policy.name = policy_name
            policy.ca_weight = config["ca_weight"]
            policy.exam_weight = config["exam_weight"]
            policy.save()
            policy.assessment_types.all().delete()
        else:
            # Create new policy
            policy = AssessmentPolicy.objects.create(
                school=school,
                term=term,
                name=policy_name,
                ca_weight=config["ca_weight"],
                exam_weight=config["exam_weight"],
                is_active=True
            )

        # Create assessment types
        for atype in config["types"]:
            AssessmentType.objects.create(policy=policy, **atype)

        return policy
