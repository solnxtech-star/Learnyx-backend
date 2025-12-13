# core/results/services.py

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import AssessmentPolicy
from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import Subject
from core.applications.grading.models import GradeScale
from core.applications.grading.models import SubjectResult
from core.applications.grading.models import TermReportSummary
from core.applications.users.models import StudentProfile as Student

# ---------------------------------------------------------------------
# Grade Mapping
# ---------------------------------------------------------------------

def map_grade_and_point(
    *,
    school,
    score: float,
) -> tuple[str | None, Decimal | None, str | None]:
    """
    Convert a numeric score into grade, grade point, and remark
    using the active GradeScale for the school.

    Returns:
        (grade, grade_point, remark)
    """
    scales = (
        GradeScale.objects.filter(school=school, is_active=True)
        .order_by("-max_score", "order")
    )

    for scale in scales:
        if scale.min_score <= score <= scale.max_score:
            return (
                scale.grade,
                Decimal(str(scale.point)),
                scale.remark,
            )

    return None, None, None


# ---------------------------------------------------------------------
# Subject Result Computation
# ---------------------------------------------------------------------

def _calculate_assessment_scores(
    *,
    student: Student,
    classroom_subject: Subject,
    policy: AssessmentPolicy,
) -> tuple[float, float, float]:
    """Calculate CA, exam, and half-term scores from assessment records."""
    total_ca: float = 0.0
    exam_score: float = 0.0
    half_term_score: float = 0.0

    for assessment_type in policy.assessment_types.all().order_by("order"):
        records = AssessmentRecord.objects.filter(
            student=student,
            classroom_subject=classroom_subject,
            assessment_type=assessment_type,
        )

        if not records.exists():
            if assessment_type.is_optional:
                continue
            average_score = 0.0
        else:
            total = sum(record.score or 0 for record in records)
            average_score = total / records.count()

        if assessment_type.category == "EXAM":
            exam_score = average_score
        elif assessment_type.category == "HALF_TERM":
            half_term_score = average_score
        else:
            total_ca += average_score * (assessment_type.weight / 100)

    return total_ca, exam_score, half_term_score


def _calculate_total_score(
    *,
    total_ca: float,
    exam_score: float,
    half_term_score: float,
    term_type: str,
    policy: AssessmentPolicy,
) -> float:
    """Calculate final score based on term type."""
    score_map = {
        "END_TERM": (
            (total_ca / 100) * policy.ca_weight
            + (exam_score / 100) * policy.exam_weight
        ),
        "HALF_TERM": total_ca + half_term_score,
    }
    total_score = score_map.get(term_type, total_ca + exam_score)
    return min(total_score, 100.0)


def _calculate_average_score(
    *,
    total_score: float,
    half_term_score: float,
    term_type: str,
) -> float | None:
    """Calculate average score for half-term reports."""
    if term_type != "HALF_TERM":
        return None
    divisor = 2 if half_term_score else 1
    return total_score / divisor


@transaction.atomic
def compute_subject_result(
    *,
    student: Student,
    classroom_subject: Subject,
    term: AcademicTerm,
) -> SubjectResult:
    """
    Compute and persist a SubjectResult for a student in a subject
    for the given academic term.

    Business Rules:
    - Missing required assessments count as 0
    - Optional assessments are skipped if missing
    - End Term = CA + Exam (weighted)
    - Half Term = CA + Half-Term score
    """

    school = classroom_subject.school

    policy = AssessmentPolicy.objects.filter(
        school=school,
        term=term,
        is_active=True,
    ).first()

    if not policy:
        msg = "No active assessment policy configured for this term."
        raise ValidationError(
            msg,
        )

    total_ca, exam_score, half_term_score = _calculate_assessment_scores(
        student=student,
        classroom_subject=classroom_subject,
        policy=policy,
    )

    total_score = _calculate_total_score(
        total_ca=total_ca,
        exam_score=exam_score,
        half_term_score=half_term_score,
        term_type=term.term_type,
        policy=policy,
    )

    grade, grade_point, remark = map_grade_and_point(
        school=school,
        score=total_score,
    )

    average_score = _calculate_average_score(
        total_score=total_score,
        half_term_score=half_term_score,
        term_type=term.term_type,
    )

    target = student.target_grades.filter(
        subject=classroom_subject.subject,
        term=term,
    ).first()

    subject_result, _ = SubjectResult.objects.update_or_create(
        student=student,
        classroom_subject=classroom_subject,
        term=term,
        defaults={
            "total_ca": total_ca,
            "exam_score": exam_score,
            "half_term_score": half_term_score or None,
            "total_score": total_score,
            "average_score": average_score,
            "grade": grade,
            "grade_point": grade_point,
            "remark": remark or "",
            "target_grade": target.target_grade if target else None,
            "target_point": target.target_point if target else None,
        },
    )

    if target and grade_point:
        target.check_achievement(grade, grade_point)

    return subject_result


# ---------------------------------------------------------------------
# Term Summary & Ranking
# ---------------------------------------------------------------------

@transaction.atomic
def compute_term_summary_for_class(
    *,
    class_group: ClassRoom,
    term: AcademicTerm,
):
    """
    Compute TermReportSummary for all students in a class
    and assign class positions.
    """

    students = Student.objects.filter(class_group=class_group)
    summaries = []

    for student in students:
        results = SubjectResult.objects.filter(
            student=student,
            term=term,
            classroom_subject__class_group=class_group,
        ).exclude(total_score__isnull=True)

        total_score = results.aggregate(
            total=Sum("total_score"),
        )["total"] or 0.0

        subject_count = results.count() or 1
        average_score = total_score / subject_count

        valid = results.exclude(grade_point__isnull=True)
        total_points = valid.aggregate(
            total=Sum("grade_point"),
        )["total"] or 0

        gpa = total_points / valid.count() if valid.exists() else 0

        target_grades = student.target_grades.filter(term=term)
        target_points = target_grades.aggregate(
            total=Sum("target_point"),
        )["total"] or 0

        target_gpa = (
            target_points / target_grades.count()
            if target_grades.exists()
            else 0
        )

        summary, _ = TermReportSummary.objects.update_or_create(
            student=student,
            term=term,
            class_group=class_group,
            defaults={
                "total_score": total_score,
                "average_score": average_score,
                "total_points": total_points,
                "gpa": round(gpa, 2),
                "target_total_points": target_points,
                "target_gpa": round(target_gpa, 2),
            },
        )

        summaries.append(summary)

    _assign_class_positions(summaries)
    return summaries


def _assign_class_positions(summaries: list[TermReportSummary]) -> None:
    """
    Assign class positions based on:
    1. Total points (DESC)
    2. Total score (DESC)
    """

    summaries.sort(
        key=lambda s: (-s.total_points, -s.total_score),
    )

    last_rank = 0
    last_values = None

    for index, summary in enumerate(summaries, start=1):
        current = (summary.total_points, summary.total_score)

        if current == last_values:
            summary.class_position = last_rank
        else:
            summary.class_position = index
            last_rank = index
            last_values = current

        summary.save(update_fields=["class_position"])


# ---------------------------------------------------------------------
# Bulk Computation
# ---------------------------------------------------------------------

@transaction.atomic
def compute_all_results_for_term(
    *,
    class_group: ClassRoom,
    term: AcademicTerm,
):
    """
    Compute all SubjectResults and TermReportSummary
    for a class and term.
    """

    subjects = Subject.objects.filter(class_group=class_group)

    for subject in subjects:
        for student in subject.students.all():
            compute_subject_result(
                student=student,
                classroom_subject=subject,
                term=term,
            )

    return compute_term_summary_for_class(
        class_group=class_group,
        term=term,
    )
