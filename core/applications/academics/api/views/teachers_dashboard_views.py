from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.applications.academics.api.schemas import teachers_dashboard
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    ClassroomStudentSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentAssessmentSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentContactSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentProfileDetailSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    TeacherClassroomSerializer,
)
from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import ClassRoom
from core.applications.users.models import StudentContact, TeacherProfile
from core.applications.users.models import StudentProfile
from core.helper.permissions import IsSchoolAdminOrAssignedTeacher


@teachers_dashboard
class TeacherDashboardViewSet(viewsets.ViewSet):
    """
    Unified ViewSet for all teacher dashboard operations.
    """

    permission_classes = [IsAuthenticated, IsSchoolAdminOrAssignedTeacher]

    def _get_teacher(self, user):
        """
        Safely resolve the teacher profile for the current user.
        Raises 404 if user has no TeacherProfile.
        """
        return get_object_or_404(
            TeacherProfile.objects.select_related("user"),
            user=user
        )

    @action(detail=False, methods=["get"], url_path="classes")
    def classes(self, request):
        """
        List classrooms assigned to the teacher.
        """
        teacher = self._get_teacher(request.user)

        classrooms = (
            ClassRoom.objects.filter(
                teaching_assignments__teacher=teacher,
                school=request.user.school,
            )
            .distinct()
            .order_by("academic_class", "arm")
        )

        serializer = TeacherClassroomSerializer(classrooms, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="classes/(?P<classroom_id>[^/.]+)/students",
    )
    def students(self, request, classroom_id=None):
        """
        List students in a specific classroom.
        """
        students = (
            StudentProfile.objects.select_related("user")
            .filter(
                classroom_id=classroom_id,
                user__school=request.user.school,
            )
            .order_by("user__name")
        )

        serializer = ClassroomStudentSerializer(students, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="students/(?P<student_id>[^/.]+)/profile",
    )
    def student_profile(self, request, student_id=None):
        """
        Retrieve detailed profile of a student.
        """
        student = get_object_or_404(
            StudentProfile.objects.select_related("user"),
            student_id=student_id,
            user__school=request.user.school,
        )

        serializer = StudentProfileDetailSerializer(student)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="students/(?P<student_id>[^/.]+)/assessments",
    )
    def student_assessments(self, request, student_id=None):
        subject_id = request.query_params.get("subject_id")

        qs = AssessmentRecord.objects.filter(
            student__student_id=student_id,
            student__user__school=request.user.school,
        )

        if subject_id:
            qs = qs.filter(classroom_subject__subject_id=subject_id)

        serializer = StudentAssessmentSerializer(qs, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="students/(?P<student_id>[^/.]+)/contacts",
    )
    def student_contacts(self, request, student_id=None):
        """
        Retrieve guardian/contact details for a student.
        """
        contacts = StudentContact.objects.filter(
            student__student_id=student_id,
            student__user__school=request.user.school,
        ).order_by("-is_primary", "name")

        serializer = StudentContactSerializer(contacts, many=True)
        return Response(serializer.data)
