import logging
from django.shortcuts import get_object_or_404
from core.applications.academics.services.teacher_student_service import TeacherStudentService
from core.applications.users.api.serializers.admin_accessment_serializers import AssessmentTypeSerializer
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)

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
    StudentSubjectMatchSerializer,
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
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    TeacherClassroomStudentsResponseSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    TeachersSubjectSerializer,
)
from core.applications.academics.models import AcademicSession
from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import AssessmentType
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import TeachingAssignment
from core.applications.grading.models import SubjectResult
from core.applications.users.models import StudentContact
from core.applications.users.models import StudentProfile
from core.applications.users.models import TeacherProfile
from core.helper.mixins import CurrentAcademicContextMixin
from core.helper.permissions import IsSchoolAdminOrAssignedTeacher
from core.helper.service import compute_subject_result


@extend_schema(tags=["Teacher Dashboard"])
@teachers_dashboard
class TeacherDashboardViewSet(
    viewsets.ViewSet
):
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
        """
        List classrooms assigned to the logged-in teacher,
        including subjects taught per classroom.

        Multi-tenant safe:
        - Scoped to teacher
        - Scoped to school
        """

        teacher = self._get_teacher(request.user)

        classrooms = (
            ClassRoom.objects
            .filter(
                teaching_assignments__teacher=teacher,
                school=request.user.school,
            )
            .distinct()
            .order_by("academic_class", "arm")
        )

        serializer = TeacherClassroomSerializer(
            classrooms,
            many=True,
            context={
                "request": request,
                "teacher": teacher,
            },
        )

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"classes/(?P<classroom_id>[^/.]+)/students",
        url_name="classroom-students"
    )
    def students(self, request, classroom_id=None):
        """
        Endpoint for teachers to view students in their assigned classroom.
        Features:
        - Multi-tenant safety (school-scoped via classroom)
        - Permission validation (teacher assigned to classroom)
        - Optimized queries via service layer
        - Clean, structured response
        """
        try:
            # 1️⃣ Get teacher profile
            teacher = self._get_teacher(request.user)

            # 2️⃣ Validate classroom exists and belongs to teacher's school
            classroom = self._validate_classroom(classroom_id, teacher.school)

            # 3️⃣ Get current academic context
            academic_context = self._get_academic_context(teacher.school)
            current_session = academic_context["session"]
            current_term = academic_context["term"]

            # 4️⃣ Ensure teacher is assigned to classroom
            TeacherStudentService.validate_teacher_classroom_assignment(
                teacher, classroom_id
            )

            # 5️⃣ Fetch students via service layer
            students = TeacherStudentService.get_students_by_teacher_subjects(
                teacher=teacher,
                classroom_id=classroom_id,
                session=current_session,
                term=current_term,
            )

            # 6️⃣ Serialize students
            serializer_context = {
                "request": request,
                "session": current_session,
                "term": current_term,
            }
            student_serializer = ClassroomStudentSerializer(
                students,
                many=True,
                context=serializer_context
            )

            # 7️⃣ Build structured response
            response_data = {
                "classroom": str(classroom),
                "classroom_id": classroom.id,
                "session": str(current_session),
                "term": str(current_term),
                "students": student_serializer.data,
                "total_students": len(students)
            }

            response_serializer = TeacherClassroomStudentsResponseSerializer(
                response_data,
                context={"request": request}
            )

            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except PermissionDenied as e:
            self.log_permission_denial(request.user, classroom_id)
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.exception(f"Error fetching classroom students: {str(e)}")
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="students-by-subject")
    def students_by_subject(self, request):
        """
        List students in the teacher's classrooms who are enrolled in
        subjects the teacher teaches.
        """
        teacher = self._get_teacher(request.user)

        # Get teaching assignments (single source of truth)
        assignments = TeachingAssignment.objects.filter(
            teacher=teacher
        ).select_related("classroom", "subject")

        classroom_ids = assignments.values_list("classroom_id", flat=True)
        subject_ids = assignments.values_list("subject_id", flat=True)

        # Students in those classrooms enrolled in those subjects
        students_qs = (
            StudentProfile.objects
            .filter(
                classroom_id__in=classroom_ids,
                subject_enrollments__subject_id__in=subject_ids,
            )
            .distinct()
            .select_related("user", "classroom")
        )

        serializer = StudentSubjectMatchSerializer(
            students_qs,
            many=True,
            context={
                "teacher_subject_ids": list(subject_ids),
            },
        )

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"students/(?P<student_id>[^/.]+)/profile",
        url_name="student-profile",
    )
    def student_profile(self, request, student_id=None):
        """
        Endpoint to fetch a single student's profile.
        Ensures multi-tenant safety: teacher can only access students from their school.
        """
        try:
            student = get_object_or_404(
                StudentProfile.objects.select_related("user"),
                student_id=student_id,
                user__school=request.user.school,  # multi-tenant safety
            )

            serializer = StudentProfileDetailSerializer(
                student, context={"request": request}
            )
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception(f"Error fetching student profile: {str(e)}")
            return Response(
                {"detail": "An error occurred while fetching the student profile."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # ------------------------------------------------------------------
    # HELPER METHODS
    # ------------------------------------------------------------------
    def _validate_classroom(self, classroom_id, school):
        """Validate that the classroom exists and belongs to the given school"""
        try:
            return ClassRoom.objects.get(id=classroom_id, school=school)
        except ClassRoom.DoesNotExist:
            raise PermissionDenied("Classroom not found or access denied.")

    def _get_academic_context(self, school):
        """Get current academic session and term for the school (teacher-only endpoint)"""
        return self.get_current_academic_context(school=school)

    def log_permission_denial(self, user, classroom_id):
        """Log permission denials for security audit"""
        logger.warning(
            f"Permission denied: User {user.id} attempted access to classroom {classroom_id}"
        )

    def _get_teacher(self, user):
        """Fetch teacher profile from user"""
        try:
            return user.teacherprofile
        except TeacherProfile.DoesNotExist:
            raise PermissionDenied("Teacher profile not found.")

        # ------------------------------------------------------------------
        # TEACHER SUBJECTS


    @action(detail=False, methods=["get"], url_path="subjects")
    def list_teacher_subjects(self, request):
        """
        List subjects the authenticated teacher is assigned to teach.
        """
        teacher = self._get_teacher(request.user)

        qs = TeachingAssignment.objects.filter(
            teacher=teacher,
            subject__is_active=True,
        ).select_related("subject", "classroom")

        classroom_id = request.query_params.get("classroom")
        if classroom_id:
            qs = qs.filter(classroom_id=classroom_id)

        serializer = TeachersSubjectSerializer(qs, many=True)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # ASSESSMENT TYPES

    @action(detail=False, methods=["get"], url_path="assessment-types")
    def list_assessment_types(self, request):
        """
        List assessment types for the active academic term.
        """
        term = self._get_term_from_assessment(
            AssessmentType.objects.filter(policy__is_active=True).first()
         )

        qs = AssessmentType.objects.filter(
            policy__term=term,
            policy__is_active=True,
        ).select_related("policy", "policy__term")

        serializer = AssessmentTypeSerializer(qs, many=True)
        return Response(serializer.data)



    # ------------------------------------------------------------------
    # ASSESSMENT ENTRY (WRITE)
    # ------------------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="assessments/enter")
    def enter_assessment(self, request):
        """
        Create an assessment entry for a student.

        Flow:
        1. Authorize teacher (classroom + subject via TeachingAssignment)
        2. Validate assessment rules
        3. Persist assessment record
        4. Compute subject result immediately
        """

        teacher = self._get_teacher(request.user)

        # ------------------------------
        # Step 1: Validate incoming payload
        # ------------------------------
        serializer = AssessmentEntryCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        student = serializer.validated_data["student"]
        subject = serializer.validated_data["subject"]

        # ------------------------------
        # Step 2: Teacher authorization
        # ------------------------------

        # Classroom check
        if not teacher.classrooms.filter(id=student.classroom_id).exists():
            logger.warning(
                "Unauthorized assessment entry attempt (classroom)",
                extra={
                    "teacher_id": teacher.id,
                    "student_id": student.id,
                    "classroom_id": student.classroom_id,
                },
            )
            raise PermissionDenied("You are not assigned to this classroom.")

        # Subject + Classroom check using TeachingAssignment
        if not TeachingAssignment.objects.filter(
            teacher=teacher,
            classroom_id=student.classroom_id,
            subject_id=subject.id,
        ).exists():
            logger.warning(
                "Unauthorized assessment entry attempt (subject assignment)",
                extra={
                    "teacher_id": teacher.id,
                    "student_id": student.id,
                    "subject_id": subject.id,
                    "classroom_id": student.classroom_id,
                },
            )
            raise PermissionDenied(
                "You are not assigned to teach this subject in this classroom."
            )

        # ------------------------------
        # Step 3: Persist assessment record
        # ------------------------------
        record = serializer.save()

        # ------------------------------
        # Step 4: Compute subject results synchronously
        # ------------------------------
        term = self._get_term_from_assessment(record.assessment_type)
        compute_subject_result(
            student=record.student,
            classroom_subject=record.classroom_subject,
            term=term,
        )

        logger.info(
            "Assessment result recomputed",
            extra={
                "student_id": record.student.id,
                "subject_id": record.classroom_subject.id,
                "term_id": term.id,
                "teacher_id": teacher.id,
            },
        )

        # ------------------------------
        # Step 5: Return serialized response
        # ------------------------------
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
        """
        List all assessments for a student, optionally filtered by subject.
         Multi-tenant safe: scoped to teacher's school
        """
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
