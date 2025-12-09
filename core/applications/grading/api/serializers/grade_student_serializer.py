# grading/serializers.py

from rest_framework import serializers
from core.applications.grading.models import GradeScale
from django.utils.translation import gettext_lazy as _


class GradingKeySerializer(serializers.ModelSerializer):
    """
    Serializer for grading key/scale for inclusion in reports.
    Shows the school's grading system at a glance.

    Example Output:
        [
            {"grade": "A", "min_score": 75, "max_score": 100, "point": 5.0},
            {"grade": "B", "min_score": 70, "max_score": 74, "point": 4.0},
            ...
        ]
    """

    score_range = serializers.SerializerMethodField(
        help_text=_("Formatted score range (e.g., '75-100')")
    )

    class Meta:
        model = GradeScale
        fields = ['grade', 'display_name', 'score_range', 'point', 'remark']

    def get_score_range(self, obj):
        """Format score range for display."""
        return f"{obj.min_score}-{obj.max_score}"
