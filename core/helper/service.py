import logging
from collections import defaultdict
from decimal import Decimal
from typing import Dict
from typing import List
from typing import Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg
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
# Logger setup
# ---------------------------------------------------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------
# GRADE SCALE LOADER
# ---------------------------------------------------------------------

def load_grade_scales(school_id: int) -> List[GradeScale]:
    """
    Load active and published grade scales for a school, ordered by max_score desc and then by order asc.
    This ensures that the highest grade scale is evaluated first when mapping scores to grades.
    Returns a list of GradeScale objects with only the necessary fields loaded.
    """
    logger.info(f"Loading grade scales for school_id={school_id}")
    scales = list(
        GradeScale.objects.filter(
            school_id=school_id,
            is_active=True,
            is_published=True,
        )
        .only("min_score", "max_score", "grade", "point", "remark")
        .order_by("-max_score", "order")
    )
    logger.info(f"Loaded {len(scales)} grade scales for school_id={school_id}")
    return scales

def map_grade(score: Decimal, scales: List[GradeScale]) -> Tuple[str, Decimal, str]:
    """
    Map a numeric score to a grade and grade point using the provided grade scales.
    The scales should be ordered by max_score descending to ensure correct mapping.
    Returns a tuple of (grade, grade_point, remark). If no scale matches, returns (None, None, None).
    """
    for scale in scales:
        if scale.min_score <= score <= scale.max_score:
            logger.debug(f"Score {score} mapped to grade {scale.grade} (point {scale.point})")
            return scale.grade, scale.point, scale.remark
    logger.warning(f"Score {score} did not match any grade scale")
    return None, None, None

# ---------------------------------------------------------------------
# POLICY LOADER
# ---------------------------------------------------------------------

def load_policy(school_id: int, term_id: int) -> AssessmentPolicy:
    """
    Load the active assessment policy for a given school and term.
    Returns an AssessmentPolicy object with only the necessary fields loaded.
    Raises ValidationError if no active policy is found.
    """

    logger.info(f"Loading assessment policy for school_id={school_id}, term_id={term_id}")
    policy = (
        AssessmentPolicy.objects.filter(
            school_id=school_id,
            term_id=term_id,
            is_active=True
        )
        .only("ca_weight", "exam_weight")
        .first()
    )
    if not policy:
        logger.error(f"No active assessment policy found for school_id={school_id}, term_id={term_id}")
        raise ValidationError("No active assessment policy configured.")
    logger.info(f"Loaded policy: CA {policy.ca_weight}%, EXAM {policy.exam_weight}%")
    return policy

# ---------------------------------------------------------------------
# AGGREGATION ENGINE
# ---------------------------------------------------------------------

def aggregate_scores(student_ids: List[int], subject_ids: List[int]) -> Dict[Tuple[int, int], Dict[str, Decimal]]:
    """
    Aggregate assessment scores for given student and subject IDs.
    Returns a dictionary keyed by (student_id, subject_id) with values containing aggregated CA,
    EXAM, and HALF_TERM scores.
     The aggregation is done in a single query to optimize performance, and the results are processed
     in Python to avoid issues with Avg on Decimal fields.
    """

    logger.info(f"Aggregating scores for {len(student_ids)} students and {len(subject_ids)} subjects")
    rows = (
        AssessmentRecord.objects.filter(
            student_id__in=student_ids,
            classroom_subject_id__in=subject_ids
        )
        .values("student_id", "classroom_subject_id", "period__period_type")
        .annotate(avg_score=Avg("score"))
    )

    data = defaultdict(lambda: {"CA": Decimal("0"), "EXAM": Decimal("0"), "HALF_TERM": Decimal("0")})

    for r in rows:
        key = (r["student_id"], r["classroom_subject_id"])
        score = Decimal(r["avg_score"] or 0)
        period = r["period__period_type"]
        if period == "EXAM":
            data[key]["EXAM"] = score
        elif period == "HALF_TERM":
            data[key]["HALF_TERM"] = score
        else:
            data[key]["CA"] += score

    logger.info(f"Aggregated scores for {len(data)} student-subject combinations")
    return data

# ---------------------------------------------------------------------
# SCORE ENGINE
# ---------------------------------------------------------------------

def compute_scores(policy: AssessmentPolicy, term: AcademicTerm, agg: Dict, student_id: int, subject_id: int) -> Tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    record = agg.get((student_id, subject_id), {})
    ca = record.get("CA", Decimal("0"))
    exam = record.get("EXAM", Decimal("0"))
    half = record.get("HALF_TERM", Decimal("0"))

    if term.term_type == "END_OF_TERM":
        total = (ca * policy.ca_weight / 100) + (exam * policy.exam_weight / 100)
    elif term.term_type == "HALF_TERM":
        total = ca
    else:
        total = ca + exam
    total = min(total, Decimal("100"))

    avg = Decimal("0")
    if term.term_type == "HALF_TERM":
        parts = [ca] + ([half] if half else [])
        avg = sum(parts) / Decimal(len(parts))

    logger.debug(f"Computed scores for student_id={student_id}, subject_id={subject_id}: CA={ca}, EXAM={exam}, HALF={half}, TOTAL={total}, AVG={avg}")
    return ca, exam, half, total, avg

# ---------------------------------------------------------------------
# SUBJECT RESULTS (BULK)
# ---------------------------------------------------------------------

@transaction.atomic
def compute_all_subject_results(class_group: ClassRoom, term: AcademicTerm) -> Dict[str, int]:
    logger.info(f"Computing all subject results for class_group={class_group.id}, term={term.id}")
    student_ids = list(Student.objects.filter(classroom=class_group).values_list("id", flat=True))
    subject_ids = list(Subject.objects.filter(class_rooms=class_group).values_list("id", flat=True))

    if not student_ids or not subject_ids:
        logger.warning(f"No students or subjects found for class_group={class_group.id}")
        return {"created": 0, "updated": 0}

    school_id = class_group.school_id
    policy = load_policy(school_id, term.id)
    scales = load_grade_scales(school_id)
    agg = aggregate_scores(student_ids, subject_ids)

    existing_results = {
        (r.student_id, r.classroom_subject_id): r
        for r in SubjectResult.objects.filter(
            student_id__in=student_ids,
            classroom_subject_id__in=subject_ids,
            term=term
        ).only(
            "id", "student_id", "classroom_subject_id",
            "total_ca", "exam_score", "half_term_score",
            "total_score", "average_score", "grade", "grade_point", "comment"
        )
    }

    to_create, to_update = [], []

    for student_id in student_ids:
        for subject_id in subject_ids:
            ca, exam, half, total, avg = compute_scores(policy, term, agg, student_id, subject_id)
            if term.term_type == "END_OF_TERM":
                grade, point, remark = map_grade(total, scales)
            else:
                grade, point, remark = None, None, "Progress assessment"

            payload = {
                "total_ca": ca, "exam_score": exam, "half_term_score": half,
                "total_score": total, "average_score": avg,
                "grade": grade, "grade_point": point, "comment": remark
            }

            key = (student_id, subject_id)
            if key in existing_results:
                obj = existing_results[key]
                for field, value in payload.items():
                    setattr(obj, field, value)
                to_update.append(obj)
            else:
                to_create.append(
                    SubjectResult(student_id=student_id, classroom_subject_id=subject_id, term=term, **payload)
                )

    if to_create:
        SubjectResult.objects.bulk_create(to_create, batch_size=1000)
        logger.info(f"Created {len(to_create)} SubjectResult records")
    if to_update:
        SubjectResult.objects.bulk_update(to_update, fields=list(payload.keys()), batch_size=1000)
        logger.info(f"Updated {len(to_update)} SubjectResult records")

    return {"created": len(to_create), "updated": len(to_update)}

# ---------------------------------------------------------------------
# TERM SUMMARY (BULK)
# ---------------------------------------------------------------------

@transaction.atomic
def compute_term_summary(class_group: ClassRoom, term: AcademicTerm) -> List[TermReportSummary]:
    """
    Compute term summaries and assign class positions for a class group.
    Uses Python-level calculation to avoid DB-level Avg on aggregated fields.
    """
    logger.info(f"Computing term summary for class_group={class_group.id}, term={term.id}")

    # Aggregate total_score and total_points per student
    rows = (
        SubjectResult.objects.filter(
            classroom_subject__class_rooms=class_group,
            term=term
        )
        .values("student_id")
        .annotate(
            total_score=Sum("total_score"),
            total_points=Sum("grade_point"),
            subject_count=Sum(1)  # count of subjects for averaging
        )
    )

    # Convert aggregates to Decimal to avoid float / Decimal errors
    def to_decimal(value):
        if value is None:
            return Decimal("0")
        return Decimal(str(value))

    aggregated = {}
    for r in rows:
        student_id = r["student_id"]
        total_score = to_decimal(r.get("total_score"))
        total_points = to_decimal(r.get("total_points"))
        subject_count = r.get("subject_count") or 1  # prevent division by zero
        avg_score = total_score / Decimal(subject_count)
        aggregated[student_id] = {
            "total_score": total_score,
            "average_score": avg_score,
            "total_points": total_points
        }

    # Fetch all students in the class
    student_ids = list(Student.objects.filter(classroom=class_group).values_list("id", flat=True))

    # Fetch existing summaries
    existing_summaries = {
        s.student_id: s
        for s in TermReportSummary.objects.filter(
            student_id__in=student_ids, class_group=class_group, term=term  # <-- fixed
        ).only("id", "student_id", "total_score", "average_score", "total_points", "gpa", "class_position")
    }

    to_create, to_update, summaries = [], [], []

    for student_id in student_ids:
        data = aggregated.get(student_id, {})
        total_score = data.get("total_score", Decimal("0"))
        avg_score = data.get("average_score", Decimal("0"))
        total_points = data.get("total_points", Decimal("0"))

        payload = {
            "total_score": total_score,
            "average_score": avg_score,
            "total_points": total_points,
            "gpa": total_points.quantize(Decimal("0.01"))
        }

        if student_id in existing_summaries:
            obj = existing_summaries[student_id]
            for field, value in payload.items():
                setattr(obj, field, value)
            to_update.append(obj)
            summaries.append(obj)
        else:
            obj = TermReportSummary(student_id=student_id, class_group=class_group, term=term, **payload)  # <-- fixed
            to_create.append(obj)
            summaries.append(obj)

    if to_create:
        TermReportSummary.objects.bulk_create(to_create, batch_size=1000)
        logger.info(f"Created {len(to_create)} TermReportSummary records")
    if to_update:
        TermReportSummary.objects.bulk_update(to_update, fields=list(payload.keys()), batch_size=1000)
        logger.info(f"Updated {len(to_update)} TermReportSummary records")

    # Assign positions in class
    _assign_positions(summaries)
    logger.info(f"Assigned class positions for {len(summaries)} students in class_group={class_group.id}")

    return summaries
# ---------------------------------------------------------------------
# CLASS POSITION ASSIGNMENT
# ---------------------------------------------------------------------

def _assign_positions(summaries: List[TermReportSummary]) -> None:
    """
    Assign class positions based on total_points and total_score.
    Handles ties: students with same points/score get same rank.
    """
    total_students = len(summaries)
    logger.info(f"Assigning class positions for {total_students} students")

    # Sort by total_points descending, then total_score descending
    summaries.sort(key=lambda s: (-s.total_points, -s.total_score))

    last_rank, last_value = 0, None
    for idx, s in enumerate(summaries, start=1):
        current = (s.total_points, s.total_score)
        if current == last_value:
            s.class_position = last_rank  # Tie: same rank
        else:
            s.class_position = idx
            last_rank, last_value = idx, current
        logger.debug(f"Student {s.student_id} assigned position {s.class_position} "
                     f"(points={s.total_points}, total_score={s.total_score})")

    TermReportSummary.objects.bulk_update(summaries, ["class_position"], batch_size=1000)

    logger.info(f"Class positions assigned successfully for {total_students} students")
    if total_students:
        logger.info(f"Top student: student_id={summaries[0].student_id}, position={summaries[0].class_position}")
        logger.info(f"Last student: student_id={summaries[-1].student_id}, position={summaries[-1].class_position}")
