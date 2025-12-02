from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.applications.academics.api.schemas import assign_teacher_classroom_schema
from core.applications.users.api.serializers.serializers import TeacherProfileSerializer
from core.applications.users.models import TeacherProfile
from core.applications.users.permissions import IsPrincipalOrSchoolOwner

from .serializers import AssignClassRoomSerializer


class TeacherViewSet(ModelViewSet):
    """
    Manages all teacher operations including:
    - Listing teachers
    - Retrieving teacher profile
    - Admin assignment of multiple classrooms
    - Teacher teaching assignments
    """

    queryset = TeacherProfile.objects.select_related("user")
    serializer_class = TeacherProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Enforce multi-tenant isolation by restricting teachers
        to the authenticated user's school.
        """
        school = self.request.user.school

        return (
            TeacherProfile.objects.filter(user__school=school)
            .select_related("user")
            .prefetch_related("classrooms")  # IMPORTANT for multiple classrooms
        )

    # ---------------------------------------------------------------------
    # ADMIN: Assign multiple classrooms to a teacher
    # ---------------------------------------------------------------------
    @assign_teacher_classroom_schema
    @action(
        methods=["POST"],
        detail=True,
        url_path="assign-classrooms",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def assign_classrooms(self, request, pk=None):
        """
        Admin assigns multiple classrooms to a teacher.
        """
        teacher = self.get_object()

        serializer = AssignClassRoomSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(teacher_profile=teacher)

        return Response(
            TeacherProfileSerializer(teacher, context={"request": request}).data
        )

    # ---------------------------------------------------------------------
    # TEACHER: Assign themselves to classrooms + subjects (multi)
    # ---------------------------------------------------------------------
    @action(
        methods=["POST"],
        detail=True,
        url_path="assign-teaching",
        permission_classes=[IsAuthenticated],
    )
    def assign_teaching(self, request, pk=None):
        """
        Teachers assign themselves to multiple classrooms and subjects.
        """
        teacher = self.get_object()

        # Only allow a teacher to assign themselves
        if request.user != teacher.user:
            return Response(
                {"detail": "You can only manage your own teaching assignments."},
                status=403,
            )

        serializer = TeachingAssignmentSerializer(
            data=request.data,
            context={"teacher": teacher, "request": request},
        )
        serializer.is_valid(raise_exception=True)

        assignments = serializer.save()

        return Response(
            {
                "message": "Teaching assignments created successfully",
                "count": len(assignments),
                "assignments": [
                    {
                        "id": a.id,
                        "classroom": str(a.classroom.id),
                        "subject": str(a.subject.id),
                    }
                    for a in assignments
                ],
            }
        )
