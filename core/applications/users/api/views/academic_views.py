from django.shortcuts import get_object_or_404
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
    Professionally aligned ViewSet for Academic Sessions.

    - School is auto-injected in serializer.
    - Only active sessions are exposed by default.
    - Soft-delete uses is_active flag.
    - Activation logic is handled entirely by serializer.
    """

    serializer_class = AcademicSessionSerializer
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]

    def get_queryset(self):
        # Only return sessions owned by this school
        return AcademicSession.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        # Serializer already injects school safely
        serializer.save()

    def perform_destroy(self, instance):
        # Soft delete
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"], url_path="open")
    def open_session(self, request, pk=None):
        session = self.get_object()
        serializer = OpenAcademicSessionSerializer()
        serializer.update(session, {})
        return Response(
            {"detail": "Academic session opened successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="close")
    def close_session(self, request, pk=None):
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
            session__school=self.request.user.school
        )

        session_id = self.request.query_params.get("session_id")
        if session_id:
            queryset = queryset.filter(session_id=session_id)

        return queryset

    def perform_create(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])


    @action(detail=True, methods=["post"], url_path="open-score-entry")
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
                {"detail": "Cannot open score entry for an inactive academic session."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Close any other active term in the same session
        AcademicTerm.objects.filter(
            session=session, is_active=True
        ).exclude(pk=term.pk).update(is_active=False)

        term.is_active = True
        term.save(update_fields=["is_active"])

        return Response(
            {
                "detail": f"{term.name} is now open for score entry.",
                "term_id": term.id,
                "is_active": term.is_active,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="close-score-entry")
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
            {
                "detail": f"{term.name} has been closed for score entry.",
                "term_id": term.id,
                "is_active": term.is_active,
            },
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
