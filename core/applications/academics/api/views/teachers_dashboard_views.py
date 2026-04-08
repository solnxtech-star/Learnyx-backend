import logging

from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
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
    BulkAssessmentEntrySerializer,
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
from core.applications.academics.models import StudentClassAssignment
from core.applications.academics.models import StudentSubjectEnrollment
from core.applications.academics.models import TeachingAssignment
from core.applications.academics.services.student_class_service import (
    get_student_active_classroom,
)
from core.applications.academics.services.student_class_service import (
    get_term_from_assessment,
)
from core.applications.academics.services.teacher_student_service import (
    TeacherStudentService,
)
from core.applications.grading.models import SubjectResult
from core.applications.users.api.serializers.admin_accessment_serializers import (
    AssessmentTypeSerializer,
)
from core.applications.users.models import StudentContact
from core.applications.users.models import StudentProfile
from core.applications.users.models import TeacherProfile
from core.helper.mixins import CurrentAcademicContextMixin
from core.helper.permissions import IsSchoolAdminOrAssignedTeacher
from core.helper.service import compute_all_subject_results, compute_term_summary

logger = logging.getLogger(__name__)

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

        # Teacher's teaching assignments
        assignments = TeachingAssignment.objects.filter(
            teacher=teacher
        ).select_related("classroom", "subject")

        classroom_ids = list(assignments.values_list("classroom_id", flat=True))
        subject_ids = list(assignments.values_list("subject_id", flat=True))

        # Students in those classrooms AND currently active
        students_qs = StudentProfile.objects.filter(
            class_assignments__classroom_id__in=classroom_ids,
            class_assignments__is_active=True,
            subject_enrollments__subject_id__in=subject_ids,
        ).distinct().select_related("user").prefetch_related(
            Prefetch(
                "subject_enrollments",
                queryset=StudentSubjectEnrollment.objects.select_related("subject")
            ),
            Prefetch(
                "class_assignments",
                queryset=StudentClassAssignment.objects.select_related("classroom").filter(is_active=True)
            )
        )

        serializer = StudentSubjectMatchSerializer(
            students_qs,
            many=True,
            context={"teacher_subject_ids": subject_ids}
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



    # -----------------------------
    # Single Assessment Entry Endpoint
    # -----------------------------
    @action(detail=False, methods=["post"], url_path="assessments/enter")
    def enter_assessment(self, request):
        teacher = self._get_teacher(request.user)
        serializer = AssessmentEntryCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        student = serializer.validated_data["student"]
        subject = serializer.validated_data["subject"]
        assessment_type = serializer.validated_data["assessment_type"]
        score = serializer.validated_data.get("score")

        student_name = student.user.name or "Student"
        classroom = get_student_active_classroom(student)

        # Teacher authorization
        if not TeachingAssignment.objects.filter(teacher=teacher, classroom=classroom, subject=subject).exists():
            raise PermissionDenied(f"You are not assigned to teach {subject.name} in {student_name}'s classroom.")

        term = get_term_from_assessment(assessment_type)

        # Validate enrollment
        if not StudentSubjectEnrollment.objects.filter(student=student, subject=subject, term=term).exists():
            raise ValidationError({"detail": f"{student_name} is not enrolled in {subject.name} for this term."})

        # Persist record
        record = AssessmentRecord.objects.create(
            student=student,
            classroom_subject=subject,
            assessment_type=assessment_type,
            score=score,
            index=serializer.get_next_index(student, subject, assessment_type),
        )

        # Compute subject results and term summary
        try:
            result_summary = compute_all_subject_results(class_group=student.class_group, term=term)
            term_summaries = compute_term_summary(class_group=student.class_group, term=term)
            logger.info(
                f"Computed subject results and term summary for classroom={student.class_group.id}, term={term.id}",
                extra={"result_summary": result_summary, "summaries_count": len(term_summaries)}
            )
        except Exception as e:
            logger.exception(f"Failed to compute results/term summary for classroom={student.class_group.id}, term={term.id}: {e}")

        logger.info(
            "Assessment record created",
            extra={"student_id": student.id, "subject_id": subject.id, "term_id": term.id, "teacher_id": teacher.id},
        )

        return Response(AssessmentEntrySerializer(record).data, status=status.HTTP_201_CREATED)


    @action(detail=False, methods=["post"], url_path="assessments/enter-bulk")
    def enter_bulk_assessments(self, request):
        teacher = self._get_teacher(request.user)
        serializer = BulkAssessmentEntrySerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        subject = serializer.validated_data["subject"]
        entries = serializer.validated_data["entries"]
        created_records = []

        # Preload teacher assignments (performance optimization)
        teacher_classrooms = set(
            TeachingAssignment.objects.filter(teacher=teacher, subject=subject).values_list("classroom_id", flat=True)
        )

        # Map classroom_id -> set of terms that need computation
        classrooms_terms_map = {}

        with transaction.atomic():
            for entry in entries:
                student = entry["student"]
                assessment_type = entry["assessment_type"]
                score = entry["score"]
                student_name = student.user.name or "Student"
                classroom = get_student_active_classroom(student)

                # Authorization
                if classroom.id not in teacher_classrooms:
                    raise PermissionDenied(
                        f"You are not assigned to teach {subject.name} in {student_name}'s classroom."
                    )

                # Term resolution & enrollment check
                term = get_term_from_assessment(assessment_type)
                if not StudentSubjectEnrollment.objects.filter(student=student, subject=subject, term=term).exists():
                    raise ValidationError(f"{student_name} is not enrolled in {subject.name} for this term.")

                # Persist record
                record = AssessmentRecord.objects.create(
                    student=student,
                    classroom_subject=subject,
                    assessment_type=assessment_type,
                    score=score,
                    index=serializer.get_next_index(student, subject, assessment_type),
                )
                created_records.append(record)

                # Track affected classroom-term
                classrooms_terms_map.setdefault(classroom, set()).add(term)

                logger.info(
                    "Bulk assessment record created",
                    extra={
                        "record_id": record.id,
                        "student_id": student.id,
                        "subject_id": subject.id,
                        "assessment_type_id": assessment_type.id,
                        "teacher_id": teacher.id,
                    },
                )

            # -------------------------------
            # Compute results once per classroom-term
            # -------------------------------
            for classroom, terms in classrooms_terms_map.items():
                for term in terms:
                    try:
                        result_summary = compute_all_subject_results(classroom, term)
                        term_summaries = compute_term_summary(classroom, term)
                        logger.info(
                            f"Computed subject results and term summary for classroom={classroom.id}, term={term.id}",
                            extra={
                                "result_summary": result_summary,
                                "summaries_count": len(term_summaries),
                            },
                        )
                    except Exception as e:
                        logger.exception(
                            f"Failed to compute results/term summary for classroom={classroom.id}, term={term.id}: {e}"
                        )

        logger.info(
            f"Bulk assessment entry completed: total_records={len(created_records)}, total_classrooms_terms={len(classrooms_terms_map)}"
        )

        return Response(AssessmentEntrySerializer(created_records, many=True).data, status=status.HTTP_201_CREATED)
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
