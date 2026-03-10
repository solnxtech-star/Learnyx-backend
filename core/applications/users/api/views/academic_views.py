from datetime import datetime
from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import filters
from rest_framework import serializers
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.applications.academics.models import AcademicSession
from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import Subject
from core.applications.academics.models import TermPeriod
from core.applications.users.api.schemas import ACADEMIC_SESSION_SCHEMA
from core.applications.users.api.schemas import ACADEMIC_TERM_SCHEMA
from core.applications.users.api.schemas import SUBJECT_SCHEMA
from core.applications.users.api.schemas import TeacherViewSetSchema
from core.applications.users.api.serializers.academic_section_serializers import (
    AcademicSessionSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    AcademicTermSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    AdminAssignClassroomsAndSubjectsSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    BulkAcademicTermSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    CloseAcademicSessionSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    OpenAcademicSessionSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    SubjectSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    TeacherDetailSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    TeacherListSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    TeacherListWithAssignmentsSerializer,
)
from core.applications.users.models import TeacherProfile
from core.applications.users.permissions import IsPrincipalOrSchoolOwner


@ACADEMIC_SESSION_SCHEMA
class AcademicSessionViewSet(viewsets.ModelViewSet):
    """
    Tenant-aware, enterprise-grade ViewSet for managing Academic Sessions.

    Design Principles:
    - Only sessions for the authenticated user's school (tenant) are accessible.
    - List endpoint supports filtering by active status and date ranges.
    - Soft delete deactivates session instead of removing it.
    - Activation/deactivation logic is delegated to serializers.
    - Expired sessions cannot be opened.
    """

    serializer_class = AcademicSessionSerializer
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]

    # -----------------------------------------------------
    # QUERYSET
    # -----------------------------------------------------
    def get_queryset(self):
        """
        Return sessions strictly for the authenticated user's school.
        Supports optional filtering:
        - active_only: boolean query param to filter active sessions
        - start_date / end_date: date range filters
        """
        school = getattr(self.request.user, "school", None)
        if not school:
            return AcademicSession.objects.none()  # Prevent cross-tenant access

        queryset = AcademicSession.objects.for_school(school).order_by("-start_date")

        # Tenant-aware filters for list
        if self.action == "list":
            # Filter by 'active_only' query param (default True)
            active_only = self.request.query_params.get("active_only", "true").lower()
            if active_only in ("true", "1"):
                queryset = queryset.filter(is_active=True)

            # Optional date range filtering
            start_date = self.request.query_params.get("start_date")
            end_date = self.request.query_params.get("end_date")
            if start_date:
                queryset = queryset.filter(start_date__gte=start_date)
            if end_date:
                queryset = queryset.filter(end_date__lte=end_date)

        return queryset

    # -----------------------------------------------------
    # CREATE
    # -----------------------------------------------------
    def perform_create(self, serializer):
        """
        Inject school (tenant) into the serializer.
        Tenant-aware serializers handle uniqueness and active session rules.
        """
        school = getattr(self.request.user, "school", None)
        if not school:
            raise serializers.ValidationError(_("Authenticated user must belong to a school."))
        serializer.save(school=school)

    # -----------------------------------------------------
    # SOFT DELETE
    # -----------------------------------------------------
    def perform_destroy(self, instance):
        """
        Soft delete by deactivating the session.
        Ensures tenant isolation.
        """
        if instance.is_active:
            instance.is_active = False
            instance.save(update_fields=["is_active"])

    # -----------------------------------------------------
    # OPEN SESSION
    # -----------------------------------------------------
    def _get_tenant_session(self, pk):
        """
        Fetch a session by ID ensuring it belongs to the authenticated user's school.
        Raises 404 if not found, 403 if cross-tenant access is attempted.
        """
        school = getattr(self.request.user, "school", None)
        try:
            session = AcademicSession.objects.get(pk=pk)
        except AcademicSession.DoesNotExist:
            raise NotFound(_("Academic session not found."))

        if not school or session.school != school:
            raise PermissionDenied(_("You cannot access a session for another school."))

        return session


    @action(detail=True, methods=["post"], url_path="open")
    @transaction.atomic
    def open_session(self, request, pk=None):
        """
        Activate a session.

        Rules:
        - Cannot open a session that has already ended.
        - Tenant-aware: only sessions belonging to the user's school.
        - Automatically deactivates other sessions for the same school.
        """
        session = self._get_tenant_session(pk)

        today = timezone.now().date()
        if session.end_date and session.end_date < today:
            return Response(
                {"detail": _("Cannot open a session that has already ended.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OpenAcademicSessionSerializer(
            instance=session, context={"request": request}
        )
        serializer.update(session, {})

        return Response(
            {"detail": _("Academic session opened successfully.")},
            status=status.HTTP_200_OK,
        )


    @action(detail=True, methods=["post"], url_path="close")
    @transaction.atomic
    def close_session(self, request, pk=None):
        """
        Deactivate a session.

        Rules:
        - Tenant-aware: only sessions belonging to the user's school.
        - Cannot close an already inactive session.
        """
        session = self._get_tenant_session(pk)

        serializer = CloseAcademicSessionSerializer(
            instance=session, context={"request": request}
        )
        serializer.update(session, {})

        return Response(
            {"detail": _("Academic session closed successfully.")},
            status=status.HTTP_200_OK,
        )

# ============================================================================
# Academic Term ViewSet
# ============================================================================
@ACADEMIC_TERM_SCHEMA
class AcademicTermViewSet(viewsets.ModelViewSet):
    """
    Tenant-aware ViewSet for managing Academic Terms.

    Features:
    - Multi-tenant safe (scoped to authenticated user's school)
    - CRUD operations for terms
    - Bulk creation of terms within a session
    - Open / Close score entry
    - Enforces single active term per session
    """

    serializer_class = AcademicTermSerializer
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]

    # ---------------------------------------------------------
    # Queryset
    # ---------------------------------------------------------
    def get_queryset(self):
        """
        Returns tenant-scoped queryset, optionally filtered by session_id.
        """
        school = self.request.user.school
        queryset = AcademicTerm.objects.for_school(school).select_related("session").order_by("term_number")

        session_id = self.request.query_params.get("session_id")
        if session_id:
            queryset = queryset.filter(session_id=session_id)

        return queryset

    # ---------------------------------------------------------
    # CRUD Operations
    # ---------------------------------------------------------
    def perform_create(self, serializer):
        """Delegate creation to serializer (handles tenant & activation logic)."""
        serializer.save()

    def perform_destroy(self, instance):
        """Soft-delete a term by deactivating it."""
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    # ---------------------------------------------------------
    # Bulk Create Terms
    # ---------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="bulk-create")
    @transaction.atomic
    def bulk_create(self, request):
        """
        Bulk create academic terms with tenant safety.
        Automatically generates First Half / Second Half TermPeriods.

        Steps:
        1. Validate request payload.
        2. Convert string dates to datetime.date objects.
        3. Create AcademicTerm objects for the tenant school.
        4. Automatically generate TermPeriods for each term.
        """
        serializer = BulkAcademicTermSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        school = request.user.school
        session = serializer.validated_data["session"]
        terms_data = serializer.validated_data["terms"]

        term_objects = []

        # -----------------------
        # Build AcademicTerm objects
        # -----------------------
        for term_data in terms_data:
            term_number = term_data["term_number"]

            # Convert string dates to datetime.date
            try:
                start_date = datetime.strptime(term_data["start_date"], "%Y-%m-%d").date()
                end_date = datetime.strptime(term_data["end_date"], "%Y-%m-%d").date()
            except ValueError:
                raise serializers.ValidationError(_("Invalid date format. Use YYYY-MM-DD."))

            if start_date > end_date:
                raise serializers.ValidationError(_("start_date cannot be after end_date."))

            term_type = term_data.get("term_type") or AcademicTermSerializer()._determine_term_type(term_number)

            term_objects.append(
                AcademicTerm(
                    school=school,
                    session=session,
                    term_number=term_number,
                    start_date=start_date,
                    end_date=end_date,
                    is_active=term_data.get("is_active", False),
                    term_type=term_type,
                )
            )

        # Bulk create terms
        created_terms = AcademicTerm.objects.bulk_create(term_objects)

        # -----------------------
        # Automatically generate TermPeriods
        # -----------------------
        period_objects = []
        for term in created_terms:
            start_date = term.start_date
            end_date = term.end_date

            # Midpoint calculation
            mid_date = start_date + (end_date - start_date) // 2

            period_objects.extend([
                TermPeriod(
                    school=school,
                    term=term,
                    name="First Half",
                    period_type=TermPeriod.PeriodType.HALF_TERM,
                    start_date=start_date,
                    end_date=mid_date,
                ),
                TermPeriod(
                    school=school,
                    term=term,
                    name="Second Half",
                    period_type=TermPeriod.PeriodType.HALF_TERM,
                    start_date=mid_date + timedelta(days=1),
                    end_date=end_date,
                )
            ])

        TermPeriod.objects.bulk_create(period_objects)

        return Response(
            {"detail": f"{len(created_terms)} terms created successfully."},
            status=status.HTTP_201_CREATED
        )

    # ---------------------------------------------------------
    # Open / Close Score Entry
    # ---------------------------------------------------------
    def _check_tenant(self, term):
        """Helper to validate term belongs to current user's school."""
        if term.school != self.request.user.school:
            raise serializers.ValidationError(_("Cross-school access denied."))

    @action(detail=True, methods=["post"], url_path="open-score-entry")
    @transaction.atomic
    def open_score_entry(self, request, pk=None):
        """Open a term for score entry, deactivating other active terms in the session."""
        term = self.get_object()
        self._check_tenant(term)

        if not term.session.is_active:
            return Response({"detail": _("Cannot open score entry for an inactive session.")},
                            status=status.HTTP_400_BAD_REQUEST)

        # Deactivate other active terms
        AcademicTerm.objects.for_school(request.user.school) \
            .filter(session=term.session, is_active=True) \
            .exclude(pk=term.pk) \
            .update(is_active=False)

        term.is_active = True
        term.save(update_fields=["is_active"])

        return Response(
            {
                "detail": f"{term.name} is now open for score entry.",
                "term_id": term.id,
                "is_active": True
            },
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["post"], url_path="close-score-entry")
    @transaction.atomic
    def close_score_entry(self, request, pk=None):
        """Close score entry for a term."""
        term = self.get_object()
        self._check_tenant(term)

        if not term.is_active:
            return Response({"detail": _("This term is already closed.")},
                            status=status.HTTP_400_BAD_REQUEST)

        term.is_active = False
        term.save(update_fields=["is_active"])

        return Response(
            {
                "detail": f"{term.name} is now closed for score entry.",
                "term_id": term.id,
                "is_active": False
            },
            status=status.HTTP_200_OK
        )
# ============================================================================
# Subject ViewSet
# ============================================================================


@SUBJECT_SCHEMA
class SubjectViewSet(viewsets.ModelViewSet):
    """
    Tenant-aware CRUD operations for Subjects.

    Access:
    - Only School Owners and Principals can manage subjects.

    Features:
    - Automatically assigns the authenticated user's school.
    - Classroom ownership is validated by serializer.
    - Soft deletes supported (is_active=False).
    - Searchable by name.
    """

    serializer_class = SubjectSerializer
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]

    def get_queryset(self):
        """
        Return subjects scoped to the authenticated user's school.
        Only active subjects are returned by default.
        """
        school = getattr(self.request.user, "school", None)
        if not school:
            return Subject.objects.none()

        # Tenant-aware queryset, only active subjects
        return Subject.objects.for_school(school).filter(is_active=True).prefetch_related(
            "class_rooms", "class_rooms__form_teacher__user",
        )

    @transaction.atomic
    def perform_create(self, serializer):
        """
        Assign the current user's school automatically.
        """
        serializer.save(school=self.request.user.school)

    @transaction.atomic
    def perform_update(self, serializer):
        """
        Update subject within the tenant scope.
        """
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        """
        Soft-delete: mark the subject inactive instead of deleting.
        """
        instance.is_active = False
        instance.save(update_fields=["is_active"])


@extend_schema(tags=["Teacher Management"])
@TeacherViewSetSchema
class TeacherViewSet(viewsets.ModelViewSet):
    """
    Teacher Management ViewSet.

    Responsibilities:
        - List teachers (lightweight)
        - Retrieve teacher info (detailed with assignments)
        - Admin assigns classrooms and subjects
        - Teachers create/update teaching assignments

    Multi-Tenancy:
        Restricts all returned teachers to the authenticated user's school.
    """
    queryset = TeacherProfile.objects.select_related("user")
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]
    # pagination_class = StandardResultsSetPagination

    # Enable search, filter, and ordering
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["user__name", "user__email", "staff_id", "department"]
    ordering_fields = ["user__name", "staff_id", "department"]
    ordering = ["user__name"]

    # ------------------------------
    # Serializer selection per action
    # ------------------------------
    def get_serializer_class(self):
        action_serializers = {
            "list": TeacherListSerializer,
            "retrieve": TeacherDetailSerializer,
            "list_with_assignments": TeacherListWithAssignmentsSerializer,
            "assign_classrooms_subjects": AdminAssignClassroomsAndSubjectsSerializer,
        }
        return action_serializers.get(self.action, TeacherDetailSerializer)

    # ------------------------------
    # Scoped queryset for multi-tenancy
    # ------------------------------
    def get_queryset(self):
        """
        Limit all teacher queries to the authenticated user's school.
        Prefetch related classrooms and subjects for efficiency.
        """
        school = self.request.user.school
        return (
            TeacherProfile.objects.filter(user__school=school)
            .select_related("user")
            .prefetch_related(
                "teaching_assignments__classroom",
                "teaching_assignments__subject",
                "classrooms",
                "subjects",
            )
        )

    # ------------------------------
    # Admin-only: Assign Classrooms & Subjects
    # ------------------------------
    @action(
        methods=["POST"],
        detail=True,
        url_path="assign-classrooms-subjects",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def assign_classrooms_subjects(self, request, pk=None):
        """
        Admin endpoint to assign classrooms and subjects to a teacher.
        Fully transactional, handles duplicates, and updates TeachingAssignments.
        """
        teacher = self.get_object()

        serializer = AdminAssignClassroomsAndSubjectsSerializer(
            data=request.data,
            context={"request": request, "teacher": teacher}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "message": "Classrooms and subjects assigned successfully.",
            "teacher": TeacherDetailSerializer(teacher, context={"request": request}).data,
        }, status=200)

    # ------------------------------
    # List teachers with teaching assignments (Admin)
    # ------------------------------
    @action(
        methods=["GET"],
        detail=False,
        url_path="list-with-assignments",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def list_with_assignments(self, request):
        """
        Returns all teachers in the school with their classrooms and subjects.
        Supports search, filter, ordering, and pagination.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        serializer = TeacherListWithAssignmentsSerializer(
            page or queryset,
            many=True,
            context={"request": request}
        )

        if page is not None:
            return self.get_paginated_response(serializer.data)

        return Response(serializer.data, status=200)
