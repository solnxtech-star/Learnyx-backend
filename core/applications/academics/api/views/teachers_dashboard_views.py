from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.applications.academics.api.schemas import teachers_dashboard
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    AssessmentEntryCreateSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    AssessmentEntrySerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    ClassroomStudentSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentContactSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentProfileDetailSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentSubjectResultSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    SubjectResultSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    TeacherClassroomSerializer,
)
from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import ClassRoom
from core.applications.grading.models import SubjectResult
from core.applications.users.models import StudentContact
from core.applications.users.models import StudentProfile
from core.applications.users.models import TeacherProfile
from core.helper.permissions import IsSchoolAdminOrAssignedTeacher
from core.helper.service import compute_subject_result


@extend_schema(tags=["Teacher Dashboard"])
@teachers_dashboard
class TeacherDashboardViewSet(viewsets.ViewSet):
    """
    Unified Teacher Dashboard API.

    Responsibilities:
    - Classroom & student navigation
    - Assessment entry (WRITE)
    - Assessment viewing (READ)
    - Computed subject results (READ ONLY)
    """

    permission_classes = [
        IsAuthenticated,
        IsSchoolAdminOrAssignedTeacher,
    ]

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _get_teacher(self, user):
        return get_object_or_404(
            TeacherProfile.objects.select_related("user"),
            user=user,
        )

    def _get_term_from_assessment(self, assessment_type):
        """
        Single source of truth for term resolution.
        """
        return assessment_type.policy.term

    # ------------------------------------------------------------------
    # DASHBOARD NAVIGATION
    # ------------------------------------------------------------------

    @action(detail=False, methods=["get"], url_path="classes")
    def classes(self, request):
        teacher = self._get_teacher(request.user)

        classrooms = (
            ClassRoom.objects.filter(
                teaching_assignments__teacher=teacher,
                school=request.user.school,
            )
            .distinct()
            .order_by("academic_class", "arm")
        )

        return Response(
            TeacherClassroomSerializer(classrooms, many=True).data
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="classes/(?P<classroom_id>[^/.]+)/students",
    )
    def students(self, request, classroom_id=None):
        students = (
            StudentProfile.objects.select_related("user")
            .filter(
                classroom_id=classroom_id,
                user__school=request.user.school,
            )
            .order_by("user__name")
        )

        return Response(
            ClassroomStudentSerializer(students, many=True).data
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="students/(?P<student_id>[^/.]+)/profile",
    )
    def student_profile(self, request, student_id=None):
        student = get_object_or_404(
            StudentProfile.objects.select_related("user"),
            student_id=student_id,
            user__school=request.user.school,
        )

        return Response(
            StudentProfileDetailSerializer(student).data
        )

    # ------------------------------------------------------------------
    # ASSESSMENT ENTRY (WRITE)
    # ------------------------------------------------------------------

    @action(detail=False, methods=["post"], url_path="assessments/enter")
    def enter_assessment(self, request):
        serializer = AssessmentEntryCreateSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        record = serializer.save()

        # 🔑 Explicit service call
        compute_subject_result(
            student=record.student,
            classroom_subject=record.classroom_subject,
            term=self._get_term_from_assessment(
                record.assessment_type
            ),
        )

        return Response(
            AssessmentEntrySerializer(record).data,
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------
    # ASSESSMENT VIEWING (READ)
    # ------------------------------------------------------------------

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
        ).select_related(
            "assessment_type",
            "classroom_subject",
        )

        if subject_id:
            qs = qs.filter(classroom_subject_id=subject_id)

        return Response(
            AssessmentEntrySerializer(qs, many=True).data
        )

    # ------------------------------------------------------------------
    # SUBJECT RESULT (COMPUTED)
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=["get"],
        url_path=(
            "students/(?P<student_id>[^/.]+)/"
            "subjects/(?P<subject_id>[^/.]+)/result"
        ),
    )
    def student_subject_result(
        self, request, student_id=None, subject_id=None
    ):
        """
        PRD: Student → Subject → Final computed result
        """

        term_id = request.query_params.get("term")

        result = get_object_or_404(
            SubjectResult.objects.select_related(
                "classroom_subject"
            ),
            student__student_id=student_id,
            classroom_subject_id=subject_id,
            term_id=term_id,
            student__user__school=request.user.school,
        )

        return Response(
            SubjectResultSerializer(result).data
        )

    # ------------------------------------------------------------------
    # SUBJECT FULL VIEW (ASSESSMENTS + RESULT)
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=["get"],
        url_path=(
            "students/(?P<student_id>[^/.]+)/"
            "subjects/(?P<subject_id>[^/.]+)"
        ),
    )
    def student_subject_full(
        self, request, student_id=None, subject_id=None
    ):
        """
        PRD:
        Student → Subject → Assessments + Computed Result
        """

        term_id = request.query_params.get("term")

        assessments = (
            AssessmentRecord.objects.filter(
                student__student_id=student_id,
                classroom_subject_id=subject_id,
                student__user__school=request.user.school,
            )
            .select_related("assessment_type")
            .order_by("assessment_type__order", "index")
        )

        result = SubjectResult.objects.filter(
            student__student_id=student_id,
            classroom_subject_id=subject_id,
            term_id=term_id,
        ).first()

        serializer = StudentSubjectResultSerializer(
            {
                "assessments": assessments,
                "computed_result": result,
            }
        )

        return Response(serializer.data)

    # ------------------------------------------------------------------
    # STUDENT CONTACTS
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=["get"],
        url_path="students/(?P<student_id>[^/.]+)/contacts",
    )
    def student_contacts(self, request, student_id=None):
        contacts = StudentContact.objects.filter(
            student__student_id=student_id,
            student__user__school=request.user.school,
        ).order_by("-is_primary", "name")

        return Response(
            StudentContactSerializer(contacts, many=True).data,
        )
