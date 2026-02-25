from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import extend_schema
from rest_framework import filters
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.applications.academics.models import AcademicSession
from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import Subject
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
    Enterprise-grade ViewSet for managing Academic Sessions.

    Design Principles:
    - School context is derived from authenticated user.
    - List endpoint returns only active sessions by default.
    - Soft delete deactivates session (does not remove record).
    - Activation/deactivation rules are delegated to serializers.
    - Expired sessions cannot be opened.
    """

    serializer_class = AcademicSessionSerializer
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]

    # -----------------------------------------------------
    # QUERYSET
    # -----------------------------------------------------
    def get_queryset(self):
        """
        Restrict sessions strictly to the authenticated user's school.
        By default, only active sessions are returned on list.
        """
        queryset = AcademicSession.objects.filter(
            school=self.request.user.school
        ).order_by("-start_date")

        # Only active sessions for list view
        if self.action == "list":
            queryset = queryset.filter(is_active=True)

        return queryset

    # -----------------------------------------------------
    # CREATE
    # -----------------------------------------------------
    def perform_create(self, serializer):
        """
        School is securely injected inside the serializer.
        """
        serializer.save()

    # -----------------------------------------------------
    # SOFT DELETE
    # -----------------------------------------------------
    def perform_destroy(self, instance):
        """
        Soft delete by deactivating session.
        Historical records are preserved.
        """
        if instance.is_active:
            instance.is_active = False
            instance.save(update_fields=["is_active"])

    # -----------------------------------------------------
    # OPEN SESSION
    # -----------------------------------------------------
    @action(detail=True, methods=["post"], url_path="open")
    @transaction.atomic
    def open_session(self, request, pk=None):
        """
        Activate a session.

        Rules:
        - Cannot open a session that has already ended.
        - Activation logic (deactivating others) is handled
          by the OpenAcademicSessionSerializer.
        """
        session = self.get_object()

        today = timezone.now().date()

        if session.end_date and session.end_date < today:
            return Response(
                {"detail": "Cannot open a session that has already ended."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OpenAcademicSessionSerializer()
        serializer.update(session, {})

        return Response(
            {"detail": "Academic session opened successfully."},
            status=status.HTTP_200_OK,
        )

    # -----------------------------------------------------
    # CLOSE SESSION
    # -----------------------------------------------------
    @action(detail=True, methods=["post"], url_path="close")
    @transaction.atomic
    def close_session(self, request, pk=None):
        """
        Deactivate a session.
        """
        session = self.get_object()

        serializer = CloseAcademicSessionSerializer()
        serializer.update(session, {})

        return Response(
            {"detail": "Academic session closed successfully."},
            status=status.HTTP_200_OK,
        )

# ============================================================================
# Academic Term ViewSet
# ============================================================================
@ACADEMIC_TERM_SCHEMA
class AcademicTermViewSet(viewsets.ModelViewSet):
    """
    Professionally aligned ViewSet for Academic Terms.

    Responsibilities:
    - Scoped to user's school
    - Manages academic terms lifecycle
    - Explicit control of score entry state (open/close)
    """

    serializer_class = AcademicTermSerializer
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]

    def get_queryset(self):
        queryset = AcademicTerm.objects.filter(
            session__school=self.request.user.school,
        )
        session_id = self.request.query_params.get("session_id")
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=["post"], url_path="bulk-create")
    @transaction.atomic
    def bulk_create(self, request):
        """
        Creates multiple terms within a session in a single atomic operation.

        Expected payload:
        {
            "session": 1,
            "terms": [
                {"term_number": 1, "start_date": "2026-01-10",
                "end_date": "2026-04-05", "is_active": true
                },
                ...
            ]
        }

        Business Rules:
        - Session must exist and belong to the user's school
        - Session must be active
        - Only one term can be active at a time (including existing terms)
        - start_date must be before end_date
        - term_number must be positive
        - Duplicate term_numbers in the same session are not allowed
        - term_type is automatically set based on term_number
        """
        session_id = request.data.get("session")
        terms_data = request.data.get("terms", [])

        if not session_id or not terms_data:
            return Response(
                {"errors": "Session and terms are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = get_object_or_404(
            AcademicSession, id=session_id, school=request.user.school,
        )

        if not session.is_active:
            return Response(
                {"errors": "Cannot create terms under inactive session."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent multiple active terms
        existing_active = session.terms.filter(is_active=True).exists()
        new_active_count = sum(1 for t in terms_data if t.get("is_active"))
        if new_active_count > 1 or (existing_active and new_active_count):
            return Response(
                {"errors": "Only one term can be active at a time."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent duplicate term_numbers in the same session
        existing_numbers = set(session.terms.values_list("term_number", flat=True))
        incoming_numbers = [t.get("term_number") for t in terms_data]
        if any(num in existing_numbers for num in incoming_numbers):
            return Response(
                {"errors": "Duplicate term_number detected for this session."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine term_type automatically
        def get_term_type(term_number: int) -> str:
            if term_number in (1, 2):
                return "HALF_TERM"
            elif term_number == 3:
                return "END_OF_TERM"
            return "FULL_TERM"

        # Validate and prepare terms
        validated_terms = []
        for idx, term in enumerate(terms_data, start=1):
            try:
                term_number = int(term.get("term_number"))
                if term_number < 1:
                    raise ValueError("term_number must be a positive integer")

                start_date = parse_date(term.get("start_date"))
                end_date = parse_date(term.get("end_date"))
                if not start_date or not end_date:
                    raise ValueError("start_date and end_date must be valid dates")
                if start_date > end_date:
                    raise ValueError("start_date cannot be after end_date")

                is_active = bool(term.get("is_active", False))
                term_type = get_term_type(term_number)

                validated_terms.append(
                    AcademicTerm(
                        session=session,
                        term_number=term_number,
                        start_date=start_date,
                        end_date=end_date,
                        is_active=is_active,
                        term_type=term_type,
                    )
                )
            except ValueError as e:
                return Response({"errors": f"Term {idx}: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Bulk insert
        AcademicTerm.objects.bulk_create(validated_terms)

        response_data = [
            {"id": t.id, "term_number": t.term_number, "start_date": t.start_date, "end_date": t.end_date,
             "is_active": t.is_active, "term_type": t.term_type, "name": t.name}
            for t in validated_terms
        ]

        return Response(response_data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"], url_path="open-score-entry")
    @transaction.atomic
    def open_score_entry(self, request, pk=None):
        """
        Opens a term for score entry.

        Business Rules:
        - Only one term per session can be open at a time
        - Session must be active
        """
        term = self.get_object()
        session = term.session

        if not session.is_active:
            return Response(
                {"detail": "Cannot open score entry for an inactive session."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Close other active terms
        AcademicTerm.objects.filter(
            session=session, is_active=True
        ).exclude(pk=term.pk).update(is_active=False)

        term.is_active = True
        term.save(update_fields=["is_active"])

        return Response(
            {"detail": f"{term.name} is now open for score entry.",
             "term_id": term.id, "is_active": term.is_active},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="close-score-entry")
    @transaction.atomic
    def close_score_entry(self, request, pk=None):
        """
        Closes a term for score entry.
        """
        term = self.get_object()

        if not term.is_active:
            return Response(
                {"detail": "This term is already closed for score entry."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        term.is_active = False
        term.save(update_fields=["is_active"])

        return Response(
            {"detail": f"{term.name} has been closed for score entry.",
             "term_id": term.id, "is_active": term.is_active},
            status=status.HTTP_200_OK,
        )


# ============================================================================
# Subject ViewSet
# ============================================================================


@SUBJECT_SCHEMA
class SubjectViewSet(viewsets.ModelViewSet):
    """
    Professionally aligned ViewSet for Subjects.

    Alignment with Serializer:
    - School is enforced during save.
    - Classroom ownership is validated by serializer.
    - Supports safe soft-deletes.
    """

    serializer_class = SubjectSerializer
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]

    def get_queryset(self):
        # Only return subjects belonging to this school
        return Subject.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
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
