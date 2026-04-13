import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.applications.academics.api.schemas import accessment_record_schema
from core.applications.academics.api.schemas import teachers_dashboard
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    AssessmentEntryCreateSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    AssessmentEntrySerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    AssessmentRecordUpdateSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    BulkAssessmentEntrySerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    BulkAssessmentUpdateSerializer,
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
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    TeacherSubjectClassTermSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    resolve_stage_from_period,
)
from core.applications.academics.models import AcademicSession
from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import AssessmentType
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import StudentClassAssignment
from core.applications.academics.models import StudentSubjectEnrollment
from core.applications.academics.models import TeachingAssignment
from core.applications.academics.models import TermPeriod
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
from core.helper.permissions import IsSchoolAdminOrAssignedTeacher
from core.helper.service import compute_all_subject_results
from core.helper.service import compute_term_summary

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

    @action(detail=False, methods=["get"], url_path="teachers-subjects")
    def subjects(self, request):
        """
        List subjects taught by the logged-in teacher,
        including classroom, current academic session, and term.
        """

        try:
            teacher = self._get_teacher(request.user)

            academic_context = self._get_academic_context(teacher.school)
            current_session = academic_context["session"]
            current_term = academic_context["term"]

            assignments = (
                TeachingAssignment.objects
                .filter(
                    teacher=teacher,
                    classroom__school=teacher.school,
                )
                .select_related(
                    "subject",
                    "classroom",
                )
                .order_by(
                    "classroom__academic_class",
                    "classroom__arm",
                    "subject__name",
                )
            )

            serializer = TeacherSubjectClassTermSerializer(
                assignments,
                many=True,
                context={
                    "request": request,
                    "session": current_session,
                    "term": current_term,
                },
            )

            return Response(
                {
                    # Use serializer-safe dicts instead of str()
                    "session": {
                        "id": str(current_session.id),
                        "name": current_session.name,
                        "is_active": current_session.is_active,
                    },
                    "term": {
                        "id": str(current_term.id),
                        "name": current_term.name,
                        "term_number": current_term.term_number,
                        "term_type": current_term.term_type,
                    },
                    "total_subjects": assignments.count(),
                    "results": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception(f"Error fetching teacher subjects: {str(e)}")
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

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
        """
        Return the current academic session and term for a given school.
        Assumes your AcademicSession and AcademicTerm models have methods to get the current ones.
        """
        # Example: get current active session
        current_session = AcademicSession.objects.filter(school=school, is_active=True).first()

        if not current_session:
            raise ValidationError("No active academic session found for this school.")

        # Example: get current active term in that session
        current_term = AcademicTerm.objects.filter(session=current_session, is_active=True).first()

        if not current_term:
            raise ValidationError("No active academic term found for this session.")

        return {
            "session": current_session,
            "term": current_term,
        }

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

@extend_schema(tags=["Teacher Dashboard"])
@accessment_record_schema
class TeacherAssessmentRecordViewSet(viewsets.ModelViewSet):
    """
    Handles AssessmentRecords: bulk creation, single entry, retrieval, update.
    Stage is inferred from the active TermPeriod at the time of submission.
    """

    queryset = AssessmentRecord.objects.all().select_related(
        "student", "classroom_subject", "assessment_type", "period"
    )
    permission_classes = [IsAuthenticated, IsSchoolAdminOrAssignedTeacher]

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return AssessmentEntrySerializer
        elif self.action == "create":
            return BulkAssessmentEntrySerializer
        elif self.action == "single_entry":
            return AssessmentEntryCreateSerializer
        elif self.action == "bulk_update":
            return BulkAssessmentUpdateSerializer
        elif self.action == "update":
            return AssessmentRecordUpdateSerializer
        return AssessmentEntrySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        teacher = self._get_teacher(self.request.user)
        if not teacher:
            return queryset.none()

        assignments = TeachingAssignment.objects.filter(teacher=teacher)
        query = Q()
        for assignment in assignments:
            query |= Q(
                classroom_subject_id=assignment.subject_id,
                student__classroom_id=assignment.classroom_id,
            )
        queryset = queryset.filter(query)

        student_id = self.request.query_params.get("student_id")
        classroom_id = self.request.query_params.get("classroom_id")
        subject_id = self.request.query_params.get("subject_id")
        term_id = self.request.query_params.get("term_id")
        status_param = self.request.query_params.get("status")

        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if classroom_id:
            queryset = queryset.filter(student__classroom_id=classroom_id)
        if subject_id:
            queryset = queryset.filter(classroom_subject_id=subject_id)
        if term_id:
            queryset = queryset.filter(assessment_type__policy__term_id=term_id)
        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset.order_by("-date_taken", "-id")

    def _get_teacher(self, user):
        try:
            return user.teacherprofile
        except TeacherProfile.DoesNotExist:
            return None

    def _trigger_result_computation(self, records: list):
        """
        Compute subject results and term summaries for all affected
        classroom/term/stage combinations.

        Stage is derived from the record's period type if available,
        otherwise defaults to HALF_TERM.
        """
        # Group by (classroom, term, stage)
        groups = {}

        for record in records:
            classroom = get_student_active_classroom(record.student)
            term = get_term_from_assessment(record.assessment_type)

            if not classroom or not term:
                logger.warning(
                    f"[Computation] Skipping record={record.id} — "
                    f"missing classroom or term"
                )
                continue

            # Derive stage from period type — default to HALF_TERM if no period
            if record.period and record.period.period_type == TermPeriod.PeriodType.EXAM:
                stage = SubjectResult.Stage.END_OF_TERM
            else:
                stage = SubjectResult.Stage.HALF_TERM

            key = (classroom.id, term.id, stage)
            groups.setdefault(key, (classroom, term, stage))

        for key, (classroom, term, stage) in groups.items():
            try:
                logger.info(
                    f"[Computation] Running: classroom={classroom.id}, "
                    f"term={term.id}, stage={stage}"
                )
                compute_all_subject_results(class_group=classroom, term=term, stage=stage)
                compute_term_summary(class_group=classroom, term=term, stage=stage)
            except Exception as e:
                logger.exception(
                    f"[Computation] Failed: classroom={classroom.id}, "
                    f"term={term.id}, stage={stage}: {e}"
                )

    # ---------------------------------------------------------
    # Bulk create
    # ---------------------------------------------------------

    def create(self, request, *args, **kwargs):
        teacher = self._get_teacher(request.user)
        if not teacher:
            raise PermissionDenied("Teacher profile not found.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subject = serializer.validated_data["subject"]

        teacher_classrooms = set(
            TeachingAssignment.objects.filter(teacher=teacher, subject=subject)
            .values_list("classroom_id", flat=True)
        )

        result = serializer.save()
        created_records = result["created"]
        updated_records = result["updated"]
        errors = result["errors"]

        # Filter to only records in classrooms this teacher is assigned to
        all_records = [
            r for r in created_records + updated_records
            if get_student_active_classroom(r.student) and
            get_student_active_classroom(r.student).id in teacher_classrooms
        ]

        # active_period = serializer._get_active_period()
        self._trigger_result_computation(all_records)

        return Response(
            {
                "created_count": len(created_records),
                "updated_count": len(updated_records),
                "error_count": len(errors),
                "errors": errors,
                "data": AssessmentEntrySerializer(
                    created_records + updated_records, many=True
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )

    # ---------------------------------------------------------
    # Single entry
    # ---------------------------------------------------------

    @action(detail=False, methods=["post"], url_path="single")
    def single_entry(self, request):
        teacher = self._get_teacher(request.user)
        if not teacher:
            raise PermissionDenied("Teacher profile not found.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        student = serializer.validated_data["student"]
        subject = serializer.validated_data["subject"]
        assessment_type = serializer.validated_data["assessment_type"]
        classroom = get_student_active_classroom(student)

        if not TeachingAssignment.objects.filter(
            teacher=teacher, classroom=classroom, subject=subject
        ).exists():
            raise PermissionDenied(
                f"You are not assigned to teach {subject.name} in "
                f"{getattr(student.user, 'name', 'this student')}'s classroom."
            )

        term = get_term_from_assessment(assessment_type)
        record = serializer.save()

        # Resolve active period for stage inference
        today = timezone.now().date()
        active_period = TermPeriod.objects.filter(
            term=term,
            start_date__lte=today,
            end_date__gte=today,
        ).first()

        stage = resolve_stage_from_period(active_period)

        try:
            compute_all_subject_results(class_group=classroom, term=term, stage=stage)
            compute_term_summary(class_group=classroom, term=term, stage=stage)
        except Exception as e:
            logger.exception(
                f"Result computation failed: classroom={classroom.id}, "
                f"term={term.id}, stage={stage}: {e}"
            )

        return Response(
            AssessmentEntrySerializer(record).data,
            status=status.HTTP_201_CREATED,
        )

    # ---------------------------------------------------------
    # Bulk update
    # ---------------------------------------------------------

    @action(detail=False, methods=["put"], url_path="bulk-update")
    def bulk_update(self, request):
        teacher = self._get_teacher(request.user)
        if not teacher:
            raise PermissionDenied("Teacher profile not found.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entries = serializer.validated_data["entries"]

        to_update, errors = [], []
        classrooms_terms_map = {}

        for idx, entry in enumerate(entries):
            record_id = entry.get("id")
            try:
                record = AssessmentRecord.objects.get(id=record_id)

                if record.status == "approved":
                    errors.append({
                        "index": idx,
                        "id": record_id,
                        "error": "This assessment has been approved and cannot be updated.",
                    })
                    continue

                update_serializer = AssessmentRecordUpdateSerializer(
                    instance=record, data=entry, partial=True
                )
                update_serializer.is_valid(raise_exception=True)
                updated_record = update_serializer.save()
                to_update.append(updated_record)

                classroom = get_student_active_classroom(record.student)
                if record.period and classroom:
                    classrooms_terms_map.setdefault(classroom, set()).add(
                        record.period.term
                    )

            except AssessmentRecord.DoesNotExist:
                errors.append({
                    "index": idx,
                    "id": record_id,
                    "error": f"Assessment record '{record_id}' does not exist.",
                })
            except serializers.ValidationError as e:
                errors.append({"index": idx, "id": record_id, "error": e.detail})
            except Exception as e:
                errors.append({"index": idx, "id": record_id, "error": str(e)})

        # Recompute — stage derived from the record's period
        for classroom, terms in classrooms_terms_map.items():
            for term in terms:
                # Find the period covering today within this term for stage resolution
                today = timezone.now().date()
                active_period = TermPeriod.objects.filter(
                    term=term,
                    start_date__lte=today,
                    end_date__gte=today,
                ).first()
                stage = resolve_stage_from_period(active_period)
                try:
                    compute_all_subject_results(
                        class_group=classroom, term=term, stage=stage
                    )
                    compute_term_summary(
                        class_group=classroom, term=term, stage=stage
                    )
                except Exception as e:
                    logger.exception(
                        f"Result computation failed: classroom={classroom.id}, "
                        f"term={term.id}, stage={stage}: {e}"
                    )

        return Response(
            {
                "updated_count": len(to_update),
                "error_count": len(errors),
                "errors": errors,
                "data": AssessmentEntrySerializer(to_update, many=True).data,
            },
            status=status.HTTP_200_OK,
        )
