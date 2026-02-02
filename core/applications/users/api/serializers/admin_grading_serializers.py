

from django.db import transaction
from django.db.models.functions import Trim
from django.db.models.functions import Upper
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.applications.grading.models import GradeScale


class GradeScaleSerializer(serializers.ModelSerializer):
    """
    Serializer for GradeScale model.
    Defines grade brackets and points for a school's grading system.

    Example:
        {"grade": "A1", "min_score": 75, "max_score": 100, "point": 5.0}

    Attributes:
        school_name (str): Read-only field showing school name
        score_range (str): Read-only field showing formatted score range
    """

    MAX_SCORE = 100
    MIN_SCORE = 0

    school_name = serializers.CharField(source="school.name", read_only=True)
    score_range = serializers.SerializerMethodField()

    class Meta:
        model = GradeScale
        fields = [
            "id",
            "school",
            "school_name",
            "grade",
            "display_name",
            "min_score",
            "max_score",
            "score_range",
            "point",
            "remark",
            "is_honors",
            "is_active",
            "order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "school"]

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def get_score_range(self, obj):
        """Returns formatted score range (e.g., '75-100')"""
        return f"{obj.min_score}-{obj.max_score}"

    def to_internal_value(self, data):
        """
        Normalize inputs before validation.
        Ensures grade values are clean and consistent.
        """
        internal = super().to_internal_value(data)

        if internal.get("grade"):
            internal["grade"] = internal["grade"].strip().upper()

        return internal

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------
    def validate(self, data):
        """
        Validate grade scale data.

        Ensures:
        1. min_score <= max_score
        2. Scores are between 0 and 100
        3. No overlapping score ranges within the same school
        4. Grade is unique per school (case-insensitive, trimmed)
        """
        request = self.context.get("request")
        school = request.user.school

        min_score = data.get("min_score")
        max_score = data.get("max_score")
        grade = data.get("grade")

        # =============================
        # Score range validation
        # =============================
        if min_score is not None and max_score is not None:
            if min_score > max_score:
                raise serializers.ValidationError(
                    {"min_score": _(
                        "Minimum score cannot be greater than maximum score"
                    )},
                )

            if min_score < self.MIN_SCORE or max_score > self.MAX_SCORE:
                raise serializers.ValidationError(
                    {"min_score": _("Scores must be between 0 and 100")}
                )

            overlapping = (
                GradeScale.objects
                .filter(school=school, is_active=True)
                .exclude(min_score__gt=max_score)
                .exclude(max_score__lt=min_score)
            )

            if self.instance:
                overlapping = overlapping.exclude(id=self.instance.id)

            if overlapping.exists():
                raise serializers.ValidationError(
                    {"min_score": _("Score range overlaps with an existing grade")}
                )

        # =============================
        # Grade uniqueness validation
        # =============================
        if grade:
            normalized_grade = grade.strip().upper()

            existing = (
                GradeScale.objects
                .filter(school=school, is_active=True)
                .annotate(
                    norm_grade=Upper(Trim("grade"))
                )
                .filter(norm_grade=normalized_grade)
            )

            if self.instance:
                existing = existing.exclude(id=self.instance.id)

            if existing.exists():
                raise serializers.ValidationError(
                    {"grade": _("Grade '%s' already exists for this school") % normalized_grade}
                )

        return data

class GradeScaleBulkCreateSerializer(serializers.Serializer):
    """
    Serializer for bulk creating or updating multiple grade scales (UPSERT).

    Ensures:
    - Scores fully cover 0–100 (no gaps, no overlaps)
    - Grades are normalized and unique in payload
    - Points and score ranges are valid
    """

    MAX_SCORE = 100
    MIN_SCORE = 0
    MAX_POINT = 5.0

    scales = serializers.ListField(
        child=serializers.DictField(),
        min_length=3,
        max_length=20,
        help_text=_("List of grade scale configurations"),
    )

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------
    def validate_scales(self, value):
        request = self.context["request"]

        normalized_grades = set()

        # Normalize grade values
        for scale in value:
            grade = scale.get("grade")
            if not grade or not grade.strip():
                raise serializers.ValidationError(_("Each scale must have a grade"))
            scale["grade"] = grade.strip().upper()

        # Sort by min_score
        try:
            sorted_scales = sorted(value, key=lambda x: x["min_score"])
        except KeyError:
            raise serializers.ValidationError(_("Each scale must include min_score"))

        # Must start at 0
        if sorted_scales[0]["min_score"] != self.MIN_SCORE:
            raise serializers.ValidationError(_("Grade scales must start at 0"))

        previous_max = self.MIN_SCORE - 1

        for index, scale in enumerate(sorted_scales):
            min_score = scale.get("min_score")
            max_score = scale.get("max_score")
            grade = scale.get("grade")
            point = scale.get("point")
            display_name = scale.get("display_name")
            remark = scale.get("remark")

            # -----------------------------
            # Score validation
            # -----------------------------
            if min_score is None or max_score is None:
                raise serializers.ValidationError(
                    _("Both min_score and max_score are required")
                )

            if min_score > max_score:
                raise serializers.ValidationError(
                    _("Minimum score cannot exceed maximum score")
                )

            if min_score < self.MIN_SCORE or max_score > self.MAX_SCORE:
                raise serializers.ValidationError(
                    _("Scores must be between 0 and 100")
                )

            # Gap check
            if min_score != previous_max + 1:
                raise serializers.ValidationError(
                    _("Gap detected before grade '%(grade)s'") % {"grade": grade}
                )

            # -----------------------------
            # Grade uniqueness (payload)
            # -----------------------------
            if grade in normalized_grades:
                raise serializers.ValidationError(
                    _("Duplicate grade '%(grade)s' in payload") % {"grade": grade}
                )
            normalized_grades.add(grade)

            # -----------------------------
            # Point validation
            # -----------------------------
            if point is None:
                raise serializers.ValidationError(
                    _("Each grade must define a point value")
                )

            if not (0 <= point <= self.MAX_POINT):
                raise serializers.ValidationError(
                    _("Point for '%(grade)s' must be between 0 and 5")
                    % {"grade": grade}
                )

            # -----------------------------
            # Display / remark validation
            # -----------------------------
            if display_name is not None and not display_name.strip():
                raise serializers.ValidationError(_("Display name cannot be empty"))

            if remark is not None and not remark.strip():
                raise serializers.ValidationError(_("Remark cannot be empty"))

            previous_max = max_score

        # Final coverage check
        if previous_max != self.MAX_SCORE:
            raise serializers.ValidationError(
                _("Grade scales must fully cover scores up to 100")
            )

        return value

    # ---------------------------------------------------------
    # Create / Update
    # ---------------------------------------------------------
    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        school = request.user.school

        scales = []

        for index, scale_data in enumerate(validated_data["scales"]):
            obj, _ = GradeScale.objects.update_or_create(
                school=school,
                grade=scale_data["grade"],
                defaults={
                    "display_name": scale_data.get("display_name"),
                    "min_score": scale_data["min_score"],
                    "max_score": scale_data["max_score"],
                    "point": scale_data["point"],
                    "remark": scale_data.get("remark", ""),
                    "is_honors": scale_data.get("is_honors", False),
                    "order": index + 1,
                    "is_active": True,
                },
            )
            scales.append(obj)

        return {"scales": scales}


class DefaultGradingSystemSerializer(serializers.Serializer):
    """
    Serializer for selecting a pre-configured grading system.
    Provides quick setup options for common grading systems.

    Available systems:
        - standard: Basic A-F system (Common in many schools)
        - extended: Includes A' for honors (Like in your example)
        - nigerian: Nigerian WAEC grading system (A1-F9)
        - custom: Create custom system manually
    """

    SYSTEM_CHOICES = [
        ("standard", _("Standard (A-F)")),
        ("extended", _("Extended (A'-F)")),
        ("nigerian", _("Nigerian (A1-F9)")),
        ("custom", _("Custom System")),
    ]

    system_name = serializers.ChoiceField(
        choices=SYSTEM_CHOICES, help_text=_("Select a pre-configured grading system")
    )

    def get_default_scales(self, system_name):
        """
        Get default grade scales for the selected system.

        Args:
            system_name (str): The selected grading system

        Returns:
            list: List of grade scale dictionaries

        Raises:
            serializers.ValidationError: If system_name is invalid
        """
        if system_name == "standard":
            return [
                {
                    "grade": "A",
                    "min_score": 75,
                    "max_score": 100,
                    "point": 5.0,
                    "remark": "Excellent",
                },
                {
                    "grade": "B",
                    "min_score": 70,
                    "max_score": 74,
                    "point": 4.0,
                    "remark": "Very Good",
                },
                {
                    "grade": "C",
                    "min_score": 60,
                    "max_score": 69,
                    "point": 3.0,
                    "remark": "Good",
                },
                {
                    "grade": "D",
                    "min_score": 50,
                    "max_score": 59,
                    "point": 2.0,
                    "remark": "Pass",
                },
                {
                    "grade": "E",
                    "min_score": 45,
                    "max_score": 49,
                    "point": 1.0,
                    "remark": "Poor",
                },
                {
                    "grade": "F",
                    "min_score": 0,
                    "max_score": 44,
                    "point": 0.0,
                    "remark": "Fail",
                },
            ]
        elif system_name == "extended":
            return [
                {
                    "grade": "A+",
                    "display_name": "A'",
                    "min_score": 90,
                    "max_score": 100,
                    "point": 5.0,
                    "is_honors": True,
                    "remark": "Distinction",
                },
                {
                    "grade": "A",
                    "min_score": 80,
                    "max_score": 89,
                    "point": 5.0,
                    "remark": "Excellent",
                },
                {
                    "grade": "B",
                    "min_score": 70,
                    "max_score": 79,
                    "point": 4.0,
                    "remark": "Very Good",
                },
                {
                    "grade": "C",
                    "min_score": 60,
                    "max_score": 69,
                    "point": 3.0,
                    "remark": "Good",
                },
                {
                    "grade": "D",
                    "min_score": 50,
                    "max_score": 59,
                    "point": 2.0,
                    "remark": "Pass",
                },
                {
                    "grade": "E",
                    "min_score": 40,
                    "max_score": 49,
                    "point": 1.0,
                    "remark": "Poor",
                },
                {
                    "grade": "F",
                    "min_score": 0,
                    "max_score": 39,
                    "point": 0.0,
                    "remark": "Fail",
                },
            ]
        elif system_name == "nigerian":
            return [
                {
                    "grade": "A1",
                    "min_score": 75,
                    "max_score": 100,
                    "point": 5.0,
                    "remark": "Distinction",
                },
                {
                    "grade": "B2",
                    "min_score": 70,
                    "max_score": 74,
                    "point": 4.0,
                    "remark": "Very Good",
                },
                {
                    "grade": "B3",
                    "min_score": 65,
                    "max_score": 69,
                    "point": 3.5,
                    "remark": "Good",
                },
                {
                    "grade": "C4",
                    "min_score": 60,
                    "max_score": 64,
                    "point": 3.0,
                    "remark": "Credit",
                },
                {
                    "grade": "C5",
                    "min_score": 55,
                    "max_score": 59,
                    "point": 2.5,
                    "remark": "Credit",
                },
                {
                    "grade": "C6",
                    "min_score": 50,
                    "max_score": 54,
                    "point": 2.0,
                    "remark": "Credit",
                },
                {
                    "grade": "D7",
                    "min_score": 45,
                    "max_score": 49,
                    "point": 1.5,
                    "remark": "Pass",
                },
                {
                    "grade": "E8",
                    "min_score": 40,
                    "max_score": 44,
                    "point": 1.0,
                    "remark": "Pass",
                },
                {
                    "grade": "F9",
                    "min_score": 0,
                    "max_score": 39,
                    "point": 0.0,
                    "remark": "Fail",
                },
            ]
        else:
            raise serializers.ValidationError(_("Invalid grading system"))
