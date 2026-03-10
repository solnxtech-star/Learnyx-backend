from django.db import transaction
from django.db.models.functions import Trim
from django.db.models.functions import Upper
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.applications.grading.models import GradeScale


class GradeScaleSerializer(serializers.ModelSerializer):
    """
    Serializer for single GradeScale instance (tenant-aware).

    Features:
    - Shows school name
    - Returns formatted score range
    - Validates score range and uniqueness
    """

    MAX_SCORE = 100
    MIN_SCORE = 0

    school_name = serializers.CharField(source="school.name", read_only=True)
    score_range = serializers.SerializerMethodField()

    class Meta:
        model = GradeScale
        fields = [
            "id", "school", "school_name", "grade", "display_name",
            "min_score", "max_score", "score_range", "point", "remark",
            "is_honors", "is_active", "order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "school"]

    def get_score_range(self, obj):
        return f"{obj.min_score}-{obj.max_score}"

    def to_internal_value(self, data):
        internal = super().to_internal_value(data)
        if internal.get("grade"):
            internal["grade"] = internal["grade"].strip().upper()
        return internal

    def validate(self, data):
        request = self.context.get("request")
        school = getattr(request.user, "school", None)
        if not school:
            raise serializers.ValidationError(_("No school context found"))

        grade = data.get("grade")
        min_score = data.get("min_score")
        max_score = data.get("max_score")

        # Validate score range
        if min_score is not None and max_score is not None:
            if min_score > max_score:
                raise serializers.ValidationError(
                    {"min_score": _("Minimum score cannot exceed maximum score")}
                )
            if min_score < self.MIN_SCORE or max_score > self.MAX_SCORE:
                raise serializers.ValidationError(
                    {"min_score": _("Scores must be between 0 and 100")}
                )
            overlapping = GradeScale.active_for_school(school) \
                .exclude(min_score__gt=max_score) \
                .exclude(max_score__lt=min_score)
            if self.instance:
                overlapping = overlapping.exclude(id=self.instance.id)
            if overlapping.exists():
                raise serializers.ValidationError(
                    {"min_score": _("Score range overlaps with an existing grade")}
                )

        # Validate grade uniqueness
        if grade:
            normalized = grade.strip().upper()
            existing = GradeScale.active_for_school(school) \
                .annotate(norm_grade=Upper(Trim("grade"))) \
                .filter(norm_grade=normalized)
            if self.instance:
                existing = existing.exclude(id=self.instance.id)
            if existing.exists():
                raise serializers.ValidationError(
                    {"grade": _("Grade '%s' already exists for this school") % normalized}
                )

        return data


class TenantAwareGradeScaleSerializer(serializers.Serializer):
    """
    Unified tenant-aware serializer for creating/updating grade scales.

    Supports:
    - Pre-configured systems (standard, extended, Nigerian)
    - Custom bulk scales
    Ensures:
    - Full coverage 0–100
    - No overlaps
    - Unique grades
    - Valid points (0–5)
    """

    SYSTEM_CHOICES = [
        ("standard", _("Standard (A-F)")),
        ("extended", _("Extended (A'-F)")),
        ("nigerian", _("Nigerian (A1-F9)")),
        ("custom", _("Custom System")),
    ]

    system_name = serializers.ChoiceField(
        choices=SYSTEM_CHOICES,
        help_text=_("Select a pre-configured grading system or custom")
    )
    scales = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text=_("List of custom grade scales if using 'custom'")
    )

    MAX_SCORE = 100
    MIN_SCORE = 0
    MAX_POINT = 5.0

    def get_default_scales(self, system_name):
        """Returns default grade scales for pre-configured systems."""
        defaults = {
            "standard": [
                {"grade": "A", "min_score": 75, "max_score": 100, "point": 5.0, "remark": "Excellent"},
                {"grade": "B", "min_score": 70, "max_score": 74, "point": 4.0, "remark": "Very Good"},
                {"grade": "C", "min_score": 60, "max_score": 69, "point": 3.0, "remark": "Good"},
                {"grade": "D", "min_score": 50, "max_score": 59, "point": 2.0, "remark": "Pass"},
                {"grade": "E", "min_score": 45, "max_score": 49, "point": 1.0, "remark": "Poor"},
                {"grade": "F", "min_score": 0, "max_score": 44, "point": 0.0, "remark": "Fail"},
            ],
            "extended": [
                {"grade": "A+", "display_name": "A'", "min_score": 90, "max_score": 100, "point": 5.0, "is_honors": True, "remark": "Distinction"},
                {"grade": "A", "min_score": 80, "max_score": 89, "point": 5.0, "remark": "Excellent"},
                {"grade": "B", "min_score": 70, "max_score": 79, "point": 4.0, "remark": "Very Good"},
                {"grade": "C", "min_score": 60, "max_score": 69, "point": 3.0, "remark": "Good"},
                {"grade": "D", "min_score": 50, "max_score": 59, "point": 2.0, "remark": "Pass"},
                {"grade": "E", "min_score": 40, "max_score": 49, "point": 1.0, "remark": "Poor"},
                {"grade": "F", "min_score": 0, "max_score": 39, "point": 0.0, "remark": "Fail"},
            ],
            "nigerian": [
                {"grade": "A1", "min_score": 75, "max_score": 100, "point": 5.0, "remark": "Distinction"},
                {"grade": "B2", "min_score": 70, "max_score": 74, "point": 4.0, "remark": "Very Good"},
                {"grade": "B3", "min_score": 65, "max_score": 69, "point": 3.5, "remark": "Good"},
                {"grade": "C4", "min_score": 60, "max_score": 64, "point": 3.0, "remark": "Credit"},
                {"grade": "C5", "min_score": 55, "max_score": 59, "point": 2.5, "remark": "Credit"},
                {"grade": "C6", "min_score": 50, "max_score": 54, "point": 2.0, "remark": "Credit"},
                {"grade": "D7", "min_score": 45, "max_score": 49, "point": 1.5, "remark": "Pass"},
                {"grade": "E8", "min_score": 40, "max_score": 44, "point": 1.0, "remark": "Pass"},
                {"grade": "F9", "min_score": 0, "max_score": 39, "point": 0.0, "remark": "Fail"},
            ],
        }
        try:
            return defaults[system_name]
        except KeyError:
            raise serializers.ValidationError(_("Invalid grading system"))

    def validate(self, data):
        """Validates either a pre-configured system or custom scales."""
        request = self.context.get("request")
        school = getattr(request.user, "school", None)
        if not school:
            raise serializers.ValidationError(_("No school context found"))

        system_name = data["system_name"]
        scales = data.get("scales")

        if system_name == "custom":
            if not scales:
                raise serializers.ValidationError(_("Custom system must provide scales"))
        else:
            scales = self.get_default_scales(system_name)

        self._validate_scales(scales)
        data["scales"] = scales
        return data

    def _validate_scales(self, scales):
        """Validates scales for coverage, overlaps, uniqueness, and points."""
        sorted_scales = sorted(scales, key=lambda x: x["min_score"])
        previous_max = self.MIN_SCORE - 1
        normalized_grades = set()

        for scale in sorted_scales:
            grade = scale.get("grade")
            min_score = scale.get("min_score")
            max_score = scale.get("max_score")
            point = scale.get("point")

            if not grade or not grade.strip():
                raise serializers.ValidationError(_("Each scale must have a grade"))
            scale["grade"] = grade.strip().upper()

            if min_score is None or max_score is None:
                raise serializers.ValidationError(_("Both min_score and max_score are required"))
            if min_score > max_score:
                raise serializers.ValidationError(_("Minimum score cannot exceed maximum score"))
            if min_score < self.MIN_SCORE or max_score > self.MAX_SCORE:
                raise serializers.ValidationError(_("Scores must be between 0 and 100"))
            if min_score != previous_max + 1:
                raise serializers.ValidationError(_("Gap detected before grade '%(grade)s'") % {"grade": grade})
            if grade in normalized_grades:
                raise serializers.ValidationError(_("Duplicate grade '%(grade)s' detected") % {"grade": grade})
            normalized_grades.add(grade)
            if point is None or not (0 <= point <= self.MAX_POINT):
                raise serializers.ValidationError(_("Point for '%(grade)s' must be between 0 and 5") % {"grade": grade})

            previous_max = max_score

        if previous_max != self.MAX_SCORE:
            raise serializers.ValidationError(_("Grade scales must fully cover scores up to 100"))

    @transaction.atomic
    def save_scales(self):
        """Create or update all validated scales for the tenant."""
        request = self.context.get("request")
        school = getattr(request.user, "school", None)
        created_scales = []

        for index, scale in enumerate(self.validated_data["scales"]):
            obj, _ = GradeScale.objects.update_or_create(
                school=school,
                grade=scale["grade"].strip().upper(),
                defaults={
                    "display_name": scale.get("display_name"),
                    "min_score": scale["min_score"],
                    "max_score": scale["max_score"],
                    "point": scale["point"],
                    "remark": scale.get("remark", ""),
                    "is_honors": scale.get("is_honors", False),
                    "order": index + 1,
                    "is_active": True,
                },
            )
            created_scales.append(obj)

        return created_scales
