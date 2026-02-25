
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.db.models import Q

from core.applications.academics.models import StudentSubjectEnrollment
from core.applications.academics.models import TeachingAssignment
from core.applications.users.models import StudentProfile


class TeacherStudentService:
    """Service layer for teacher-student related operations"""

    @staticmethod
    def get_teacher_assigned_subjects(teacher, classroom_id):
        """Get subjects assigned to teacher in a specific classroom"""
        return TeachingAssignment.objects.filter(
            teacher=teacher,
            classroom_id=classroom_id,
        ).values_list("subject_id", flat=True)

    @staticmethod
    def validate_teacher_classroom_assignment(teacher, classroom_id):
        """Ensure teacher is assigned to the classroom"""
        if not TeachingAssignment.objects.filter(
            teacher=teacher,
            classroom_id=classroom_id,
        ).exists():
            msg = "You are not assigned to this classroom."
            raise PermissionDenied(msg)

    @staticmethod
    def get_students_by_teacher_subjects(teacher, classroom_id, session, term):
        """
        Fetch students in a classroom who are enrolled in subjects taught by the teacher.
        Optimized to avoid N+1 queries using prefetch_related.

        Args:
            teacher (TeacherProfile): The teacher making the request
            classroom_id (UUID): Classroom to fetch students from
            session (AcademicSession): Current academic session
            term (AcademicTerm): Current term

        Returns:
            List[StudentProfile]: Students with at least one relevant subject enrollment
        """

        # 1. Get the subjects assigned to the teacher in this classroom
        subject_ids = TeacherStudentService.get_teacher_assigned_subjects(
            teacher, classroom_id
        )

        if not subject_ids:
            # Teacher teaches no subjects here, return empty queryset
            return StudentProfile.objects.none()

        # 2. Prefetch enrollments in the subjects the teacher teaches
        enrollment_prefetch = Prefetch(
            "subject_enrollments",
            queryset=StudentSubjectEnrollment.objects.filter(
                session=session,
                term=term,
                subject_id__in=subject_ids
            ).select_related("subject"),
            to_attr="relevant_enrollments"
        )

        # 3. Fetch students in the classroom
        # ✅ Removed 'school=teacher.school' — classroom already guarantees school scope
        students = StudentProfile.objects.filter(
            classroom_id=classroom_id
        ).select_related("user").prefetch_related(
            enrollment_prefetch
        ).order_by("user__name")

        # 4. Return only students with at least one relevant enrollment
        return [student for student in students if getattr(student, "relevant_enrollments", None)]
