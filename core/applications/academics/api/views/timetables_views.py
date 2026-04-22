from django.db.models import Count
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.applications.academics.api.schemas import timetable_schema
from core.applications.academics.api.serializers.timetables_serializers import (
    TimetableCreateUpdateSerializer,
)
from core.applications.academics.api.serializers.timetables_serializers import (
    TimetableDetailSerializer,
)
from core.applications.academics.api.serializers.timetables_serializers import (
    TimetableListSerializer,
)
from core.applications.academics.models import StudentClassAssignment, TeachingAssignment
from core.applications.academics.models import Timetable
from core.applications.academics.models import TimetableEntry
from core.applications.academics.services.access_service import AccessService
from core.applications.academics.services.timetable_service import TimetableService
from core.helper.enums import TimetableType
from core.helper.permissions import IsSchoolAdminOrAssignedTeacher


class TimetableFilter(django_filters.FilterSet):
    """Filtering configuration for Timetable endpoints."""

    school_id = django_filters.NumberFilter(field_name="school__id")
    class_room_id = django_filters.NumberFilter(field_name="class_room__id")
    term_id = django_filters.NumberFilter(field_name="term__id")
    session_id = django_filters.NumberFilter(field_name="academic_session__id")

    timetable_type = django_filters.ChoiceFilter(choices=TimetableType.choices)
    is_active = django_filters.BooleanFilter()

    from_date = django_filters.DateFilter(field_name="start_date", lookup_expr="gte")
    to_date = django_filters.DateFilter(field_name="end_date", lookup_expr="lte")

    class Meta:
        model = Timetable
        fields = [
            "school_id",
            "class_room_id",
            "term_id",
            "session_id",
            "timetable_type",
            "is_active",
            "from_date",
            "to_date",
        ]


@timetable_schema
class TimetableViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing timetables.

    Access Rules:
    - School Admins (Owner/Principal): Full access within their school
    - Teachers: Read-only access to assigned classrooms
    - Others: No access
    """

    queryset = (
        Timetable.objects.all()
        .annotate(entry_count=Count("entries"))
        .select_related("school", "class_room", "academic_session", "term")
        .prefetch_related("entries", "entries__subject", "entries__time_slot")
    )

    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TimetableFilter
    search_fields = ["name", "class_room__name", "school__name"]
    ordering_fields = ["start_date", "end_date", "created_at", "name"]
    ordering = ["-start_date"]

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------
    def get_permissions(self):
        admin_actions = [
            "create",
            "update",
            "partial_update",
            "destroy",
            "activate",
            "clone",
            "remove_entry",
        ]

        if self.action in admin_actions:
            return [IsAuthenticated(), IsSchoolAdminOrAssignedTeacher()]

        return [IsAuthenticated()]

    # ------------------------------------------------------------------
    # Serializers
    # ------------------------------------------------------------------
    def get_serializer_class(self):
        if self.action == "list":
            return TimetableListSerializer
        if self.action in ["create", "update", "partial_update"]:
            return TimetableCreateUpdateSerializer
        if self.action == "retrieve":
            return TimetableDetailSerializer
        return TimetableListSerializer

    # ------------------------------------------------------------------
    # Queryset scoping
    # ------------------------------------------------------------------
    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if AccessService.is_school_admin(user):
            return qs.filter(school=user.school)

        if user.role == "teacher":
            return qs.filter(
                class_room__teachingassignment__teacher=user,
                class_room__teachingassignment__school=user.school,
                school=user.school,
            ).distinct()

        if user.role == "student":
            return qs.filter(
                class_room__student_assignments__student__user=user,
                class_room__student_assignments__is_active=True,
                class_room__school=user.school,
                school=user.school,
            ).distinct()

        return qs.none()
    def perform_create(self, serializer):
        user = self.request.user
        AccessService.enforce_admin(user)
        serializer.save(school=user.school)

    def perform_update(self, serializer):
        user = self.request.user
        instance = self.get_object()

        AccessService.enforce_admin(user)
        AccessService.enforce_school(user, instance)

        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user

        AccessService.enforce_admin(user)
        AccessService.enforce_school(user, instance)

        instance.delete()

    # ------------------------------------------------------------------
    # Custom Actions
    # ------------------------------------------------------------------
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a timetable (and deactivate others if applicable)."""
        timetable = self.get_object()

        AccessService.enforce_admin(request.user)
        AccessService.enforce_school(request.user, timetable)

        TimetableService.activate(timetable)

        return Response({"message": _("Timetable activated successfully")})

    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        """Clone a timetable along with its entries."""
        timetable = self.get_object()

        AccessService.enforce_admin(request.user)
        AccessService.enforce_school(request.user, timetable)

        name = request.data.get("name", f"{timetable.name} (Copy)")
        cloned = TimetableService.clone(timetable, name)

        return Response(
            TimetableDetailSerializer(cloned).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"remove-entry/(?P<entry_id>[^/.]+)",
    )
    def remove_entry(self, request, pk=None, entry_id=None):
        """Remove a specific entry from a timetable."""
        timetable = self.get_object()

        AccessService.enforce_admin(request.user)
        AccessService.enforce_school(request.user, timetable)

        try:
            entry = timetable.entries.get(id=entry_id)
            entry.delete()
        except TimetableEntry.DoesNotExist:
            return Response(
                {"error": _("Entry not found")},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"message": _("Entry removed successfully")})
