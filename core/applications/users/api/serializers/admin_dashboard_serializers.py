

from rest_framework import serializers


class ErrorDetailSerializer(serializers.Serializer):
    """Standard DRF error envelope returned on 4xx responses."""

    detail = serializers.CharField(
        help_text="Human-readable description of the error."
    )



class TermStatusSerializer(serializers.Serializer):
    """Serializes the currently active academic term and its parent session."""

    term_name    = serializers.CharField()
    session_name = serializers.CharField()
    term_number  = serializers.IntegerField()
    status       = serializers.ChoiceField(choices=["Open", "Closed"])
    start_date   = serializers.DateField()
    end_date     = serializers.DateField()



class AcademicOverviewSerializer(serializers.Serializer):
    """Aggregate counts displayed in the dashboard overview cards."""

    active_classes  = serializers.IntegerField(min_value=0)
    total_students  = serializers.IntegerField(min_value=0)
    total_subjects  = serializers.IntegerField(min_value=0)
    total_teachers  = serializers.IntegerField(min_value=0)




class GenderDistributionSerializer(serializers.Serializer):
    """
    Percentage breakdown of student genders.

    Example:
        {"male": 65.0, "female": 35.0}

    Keys are lowercase gender values from StudentProfile.gender.
    Values are percentages rounded to one decimal place.
    Unknown / blank gender values are collected under "other".
    """

    def to_representation(self, instance: dict) -> dict:
        return instance


class ActivityItemSerializer(serializers.Serializer):
    """A single entry in the recent-activity feed."""

    label      = serializers.CharField(
        help_text="Human-readable description of the action (e.g. 'Subject Updated')."
    )
    identifier = serializers.CharField(
        help_text="Short code or name that identifies the affected record."
    )
    timestamp  = serializers.DateTimeField(
        help_text="ISO-8601 UTC timestamp of the action."
    )
    category   = serializers.ChoiceField(
        choices=["subject", "term", "session", "assignment", "enrollment", "result"],
        help_text="Machine-readable category for client-side icon / colour mapping."
    )



class DashboardSerializer(serializers.Serializer):
    """
    Root serializer for GET /api/v1/academics/dashboard/.

    Composes all dashboard sections into a single response envelope.
    Accepts a plain dict from DashboardService — no ORM instance required.
    """

    overview             = AcademicOverviewSerializer()
    current_term         = TermStatusSerializer(allow_null=True)
    gender_distribution  = GenderDistributionSerializer()
    recent_activity      = ActivityItemSerializer(many=True)
