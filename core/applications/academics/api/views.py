from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.applications.users.models import TeacherProfile
from core.applications.users.permissions import IsPrincipalOrSchoolOwner

from .serializers import AssignClassRoomSerializer
from core.applications.users.api.serializers.serializers import TeacherProfileSerializer
from rest_framework.permissions import IsAuthenticated
from core.applications.academics.api.schemas import assign_teacher_classroom_schema

class TeacherViewSet(ModelViewSet):
    queryset = TeacherProfile.objects.select_related("user")
    serializer_class = TeacherProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            TeacherProfile.objects
            .filter(user__school=self.request.user.school)
            .select_related("user", "classroom")
        )

    @assign_teacher_classroom_schema
    @action(
        methods=["POST"],
        detail=True,
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
        url_path="assign-classroom",
    )
    def assign_classroom(self, request, pk=None):
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
