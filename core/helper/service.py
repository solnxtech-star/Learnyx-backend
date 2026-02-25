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
    using the active & published GradeScale for the school.
    """

    scales = (
        GradeScale.objects.filter(
            school=school,
            is_active=True,
            is_published=True,   # ✅ IMPORTANT
        )
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
# Assessment Computation
# ---------------------------------------------------------------------

def _calculate_assessment_components(
    *,
    student: Student,
    classroom_subject: Subject,
    policy: AssessmentPolicy,
) -> tuple[float, float, float]:
    """
    Compute:
        - total_ca (0–100)
        - exam_score (0–100)
        - half_term_score (0–100)
    """

    total_ca = Decimal("0")
    exam_score = Decimal("0")
    half_term_score = Decimal("0")

    assessment_types = policy.assessment_types.all().order_by("order")

    for assessment_type in assessment_types:
        records = AssessmentRecord.objects.filter(
            student=student,
            classroom_subject=classroom_subject,
            assessment_type=assessment_type,
        )

        if not records.exists():
            if assessment_type.is_optional:
                continue
            average_percentage = Decimal("0")
        else:
            total_percentage = sum(
                Decimal(record.percentage_score or 0)
                for record in records
            )
            average_percentage = total_percentage / Decimal(records.count())

        if assessment_type.category == "EXAM":
            exam_score = average_percentage

        elif assessment_type.category == "HALF_TERM":
            half_term_score = average_percentage

        else:
            # CA components are weighted INSIDE CA only
            weight_fraction = Decimal(assessment_type.weight) / Decimal("100")
            total_ca += average_percentage * weight_fraction

    return (
        float(total_ca),
        float(exam_score),
        float(half_term_score),
    )


# ---------------------------------------------------------------------
# Score Calculations
# ---------------------------------------------------------------------

def _calculate_final_score(
    *,
    total_ca: float,
    exam_score: float,
    half_term_score: float,
    term: AcademicTerm,
    policy: AssessmentPolicy,
) -> float:
    """
    Calculate final score based on term type.
    """

    if term.term_type == "END_OF_TERM":
        final_score = (
            (total_ca * policy.ca_weight) / 100
            + (exam_score * policy.exam_weight) / 100
        )

    elif term.term_type == "HALF_TERM":
        # ✅ FIX: Half-term is CA ONLY
        final_score = total_ca

    else:  # FULL_TERM or fallback
        final_score = total_ca + exam_score

    return min(float(final_score), 100.0)


def _calculate_average_score(
    *,
    total_ca: float,
    half_term_score: float,
    term: AcademicTerm,
) -> float | None:
    """
    Average score applies ONLY to HALF_TERM.
    """

    if term.term_type != "HALF_TERM":
        return None

    scores = [total_ca]

    if half_term_score:
        scores.append(half_term_score)

    return sum(scores) / len(scores)


# ---------------------------------------------------------------------
# Subject Result Computation
# ---------------------------------------------------------------------

@transaction.atomic
def compute_subject_result(
    *,
    student: Student,
    classroom_subject: Subject,
    term: AcademicTerm,
) -> SubjectResult:
    """
    Compute and persist a SubjectResult.
    SINGLE source of truth.
    """

    school = classroom_subject.school

    policy = (
        AssessmentPolicy.objects.filter(
            school=school,
            term=term,
            is_active=True,
        )
        .first()
    )

    if not policy:
        msg = "No active assessment policy configured for this term."
        raise ValidationError(
            msg
        )

    # -------------------------------
    # Compute assessment components
    # -------------------------------
    total_ca, exam_score, half_term_score = _calculate_assessment_components(
        student=student,
        classroom_subject=classroom_subject,
        policy=policy,
    )

    total_score = _calculate_final_score(
        total_ca=total_ca,
        exam_score=exam_score,
        half_term_score=half_term_score,
        term=term,
        policy=policy,
    )

    average_score = _calculate_average_score(
        total_ca=total_ca,
        half_term_score=half_term_score,
        term=term,
    )

    # -------------------------------
    # Grade mapping (END OF TERM ONLY)
    # -------------------------------
    if term.term_type == "END_OF_TERM":
        grade, grade_point, comment = map_grade_and_point(
            school=school,
            score=total_score,
        )
    else:
        grade = None
        grade_point = None
        comment = "Progress assessment"

    # -------------------------------
    # Persist result
    # -------------------------------
    subject_result, _ = SubjectResult.objects.update_or_create(
        student=student,
        classroom_subject=classroom_subject,
        term=term,
        defaults={
            "total_ca": total_ca,
            "exam_score": exam_score,
            "half_term_score": half_term_score,
            "total_score": total_score,
            "average_score": average_score or 0,
            "grade": grade,
            "grade_point": grade_point,
            "comment": comment,
        },
    )

    return subject_result


# ---------------------------------------------------------------------
# Term Summary & Ranking
# ---------------------------------------------------------------------

@transaction.atomic
def compute_term_summary_for_class(
    *,
    class_group: ClassRoom,
    term: AcademicTerm,
) -> list[TermReportSummary]:
    """
    Compute TermReportSummary and assign positions.
    """

    students = Student.objects.filter(class_group=class_group)
    summaries: list[TermReportSummary] = []

    for student in students:
        results = SubjectResult.objects.filter(
            student=student,
            term=term,
            classroom_subject__class_rooms=class_group,
        ).exclude(total_score__isnull=True)

        total_score = results.aggregate(
            total=Sum("total_score"),
        )["total"] or 0.0

        subject_count = results.count() or 1
        average_score = total_score / subject_count

        valid_results = results.exclude(grade_point__isnull=True)

        total_points = valid_results.aggregate(
            total=Sum("grade_point"),
        )["total"] or 0

        gpa = (
            total_points / valid_results.count()
            if valid_results.exists()
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
            },
        )

        summaries.append(summary)

    _assign_class_positions(summaries)
    return summaries


def _assign_class_positions(
    summaries: list[TermReportSummary],
) -> None:
    """
    Rank by:
        1. Total points
        2. Total score
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
    Compute all SubjectResults and TermReportSummary.
    """

    subjects = Subject.objects.filter(class_rooms=class_group)

    for subject in subjects:
        students = Student.objects.filter(class_group=class_group)

        for student in students:
            compute_subject_result(
                student=student,
                classroom_subject=subject,
                term=term,
            )

    return compute_term_summary_for_class(
        class_group=class_group,
        term=term,
    )
