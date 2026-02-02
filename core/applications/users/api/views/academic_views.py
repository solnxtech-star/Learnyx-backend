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
from core.applications.academics.models import TeachingAssignment
from core.applications.users.api.schemas import ACADEMIC_SESSION_SCHEMA
from core.applications.users.api.schemas import ACADEMIC_TERM_SCHEMA
from core.applications.users.api.schemas import SUBJECT_SCHEMA
from core.applications.users.api.schemas import TeacherViewSetSchema
from core.applications.users.api.serializers.academic_section_serializers import (
    AcademicSessionSerializer,
    TeacherListWithAssignmentsSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    AcademicTermSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    AdminAssignClassroomsSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    AdminAssignSubjectsSerializer,
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
    TeacherCreateTeachingAssignmentsSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    TeacherDetailSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    TeacherListSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    TeacherReassignTeachingAssignmentSerializer,
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

    Provides:
    - List teachers
    - Retrieve teacher info
    - Admin assigns classrooms
    - Admin assigns subjects
    - Teachers create multiple teaching assignments
    - Teachers update an existing assignment

    Multi-Tenancy:
    Restricts all returned teachers to the authenticated user's school.
    """

    queryset = TeacherProfile.objects.select_related("user")
    permission_classes = [IsAuthenticated]

    # ---------------------------------------------------------
    # Dynamic serializer selection
    # ---------------------------------------------------------
    def get_serializer_class(self):
        """
        Pick serializer based on action.
        """
        action_map = {
            "list": TeacherListSerializer,
            "retrieve": TeacherDetailSerializer,
            "assign_classrooms": AdminAssignClassroomsSerializer,
            "assign_subjects": AdminAssignSubjectsSerializer,
            "assign_teaching": TeacherCreateTeachingAssignmentsSerializer,
            "reassign_teaching": TeacherReassignTeachingAssignmentSerializer,
        }
        return action_map.get(self.action, TeacherDetailSerializer)

    # ---------------------------------------------------------
    # Queryset with multi-tenancy scoping
    # ---------------------------------------------------------
    def get_queryset(self):
        """
        Only return teachers belonging to the logged-in user's school.
        """
        school = self.request.user.school
        return (
            TeacherProfile.objects.filter(user__school=school)
            .select_related("user")
            .prefetch_related("classrooms", "subjects")
        )

    # =========================================================
    # ADMIN → Assign Classrooms
    # =========================================================
    @action(
        methods=["POST"],
        detail=True,
        url_path="assign-classrooms",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def assign_classrooms(self, request, pk=None):
        """
        Admin assigns classrooms to a teacher.
        This replaces all their current classrooms.
        """
        teacher = self.get_object()

        serializer = AdminAssignClassroomsSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(teacher_profile=teacher)

        return Response(
            {
                "message": "Classrooms assigned successfully.",
                "teacher": TeacherDetailSerializer(teacher).data,
            }
        )

    # =========================================================
    # ADMIN → Assign Subjects
    # =========================================================
    @action(
        methods=["POST"],
        detail=True,
        url_path="assign-subjects",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def assign_subjects(self, request, pk=None):
        """
        Admin assigns subjects to a teacher.
        """
        teacher = self.get_object()

        serializer = AdminAssignSubjectsSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(teacher_profile=teacher)

        return Response(
            {
                "message": "Subjects assigned successfully.",
                "teacher": TeacherDetailSerializer(teacher).data,
            }
        )

    # =========================================================
    # TEACHER → Bulk Create Assignments
    # =========================================================
    @action(
        methods=["POST"],
        detail=True,
        url_path="assign-teaching",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def assign_teaching(self, request, pk=None):
        """
        Admin assigns multiple classroom+subject combinations to a teacher.
        """
        teacher = self.get_object()

        if request.user != teacher.user:
            return Response(
                {"detail": "You cannot assign teaching for another teacher."},
                status=403,
            )

        serializer = TeacherCreateTeachingAssignmentsSerializer(
            data=request.data, context={"teacher": teacher}
        )
        serializer.is_valid(raise_exception=True)
        assignments = serializer.save()

        return Response(
            {
                "message": "Teaching assignments created.",
                "count": len(assignments),
            }
        )

    # =========================================================
    # TEACHER → Reassign a Single Teaching Combination
    # =========================================================
    @action(
        methods=["PATCH"],
        detail=True,
        url_path="reassign-teaching/(?P<assignment_id>[^/.]+)",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def reassign_teaching(self, request, pk=None, assignment_id=None):
        """
        Teacher updates one of their existing teaching assignments.
        """
        teacher = self.get_object()

        if request.user != teacher.user:
            return Response(
                {"detail": "You cannot modify teaching for another teacher."},
                status=403,
            )

        try:
            assignment = TeachingAssignment.objects.get(
                id=assignment_id, teacher=teacher
            )
        except TeachingAssignment.DoesNotExist:
            return Response({"detail": "Teaching assignment not found."}, status=404)

        serializer = TeacherReassignTeachingAssignmentSerializer(
            data=request.data, context={"teacher": teacher, "assignment": assignment}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({"message": "Teaching assignment updated."})

    @action(
        methods=["GET"],
        detail=False,  # Not detail=True, because it's a list of all teachers
        url_path="list-with-assignments",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def list_with_assignments(self, request):
        """
        List all teachers in the school with classrooms and subjects assigned.
        """
        school = request.user.school
        teachers = TeacherProfile.objects.filter(user__school=school).prefetch_related(
            "classrooms", "subjects",
        )
        serializer = TeacherListWithAssignmentsSerializer(teachers, many=True)
        return Response(serializer.data)
