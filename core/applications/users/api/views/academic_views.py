from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.applications.academics.models import AcademicSession, AcademicTerm, Subject
from core.applications.users.api.schemas import (
    ACADEMIC_SESSION_SCHEMA,
    ACADEMIC_TERM_SCHEMA,
    TeacherViewSetSchema,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    AcademicSessionSerializer,
    AcademicTermSerializer,
    AdminAssignClassroomsSerializer,
    AdminAssignSubjectsSerializer,
    SubjectSerializer,
    TeacherCreateTeachingAssignmentsSerializer,
    TeacherDetailSerializer,
    TeacherListSerializer,
    TeacherReassignTeachingAssignmentSerializer,
)

from core.applications.users.models import TeacherProfile
from core.applications.users.permissions import IsPrincipalOrSchoolOwner
from drf_spectacular.utils import extend_schema


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


# ============================================================================
# Academic Term ViewSet
# ============================================================================
@ACADEMIC_TERM_SCHEMA
class AcademicTermViewSet(viewsets.ModelViewSet):
    """
    Professionally aligned ViewSet for Academic Terms.

    Alignment with Serializer:
    - Serializer enforces allowed term names.
    - Prevents activation when session is inactive.
    - Prevents duplicates.
    - View enforces school scoping and optional filtering.
    """

    serializer_class = AcademicTermSerializer
    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]

    def get_queryset(self):
        queryset = AcademicTerm.objects.filter(session__school=self.request.user.school)

        # Optional query filter
        session_id = self.request.query_params.get("session_id")
        if session_id:
            queryset = queryset.filter(session_id=session_id)

        return queryset

    def perform_create(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])


# ============================================================================
# Subject ViewSet
# ============================================================================


@ACADEMIC_TERM_SCHEMA
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
        permission_classes=[IsAuthenticated],
    )
    def assign_teaching(self, request, pk=None):
        """
        Teachers assign themselves to multiple classroom+subject combinations.
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
        permission_classes=[IsAuthenticated],
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
