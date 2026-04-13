import logging
from decimal import Decimal
from typing import Dict
from typing import List
from typing import Tuple

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
from core.helper.enums import ReviewStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# GRADE SCALE LOADER
# ---------------------------------------------------------------------

def load_grade_scales(school_id: int) -> List[GradeScale]:
    """
    Load active grade scales for a school.
    Only requires is_active=True — is_published is a student-facing concern
    and should not gate internal result computation.
    Ordered by min_score descending so the highest band is evaluated first.
    """
    logger.info("Loading grade scales for school_id=%s", school_id)

    scales = list(
        GradeScale.objects.filter(
            school_id=school_id,
            is_active=True,        # must be active
            # is_published removed — not relevant for computation
        )
        .only("min_score", "max_score", "grade", "point", "remark")
        .order_by("-max_score", "order")
    )

    if not scales:
        logger.error(
            "No active grade scales found for school_id=%s — "
            "grades cannot be assigned until scales are configured and activated.",
            school_id
        )
    else:
        logger.info("Loaded %d grade scales for school_id=%s", len(scales), school_id)

    return scales


def map_grade(score: Decimal, scales: List[GradeScale]) -> Tuple[str, Decimal, str]:
    """
    Map a numeric score to a grade, grade point, and remark.
    Normalises score and scale boundaries to 2 decimal places
    before comparison to avoid precision mismatch from DB aggregation.
    Returns (None, None, None) if no scale matches.
    """
    if score is None:
        logger.warning("map_grade received None score — skipping")
        return None, None, None

    try:
        normalised = Decimal(score).quantize(Decimal("0.01"))
    except Exception as e:
        logger.warning("map_grade could not normalise score=%s: %s", score, e)
        return None, None, None

    for scale in scales:
        try:
            min_score = Decimal(str(scale.min_score)).quantize(Decimal("0.01"))
            max_score = Decimal(str(scale.max_score)).quantize(Decimal("0.01"))
        except Exception as e:
            logger.warning(
                "map_grade could not normalise scale id=%s min=%s max=%s: %s",
                scale.id, scale.min_score, scale.max_score, e
            )
            continue

        if min_score <= normalised <= max_score:
            logger.debug(
                "Score %s → grade=%s point=%s",
                normalised, scale.grade, scale.point
            )
            return scale.grade, scale.point, scale.remark

    logger.warning(
        "Score %s did not match any grade scale — %d scales checked",
        normalised, len(scales)
    )
    return None, None, None


# ---------------------------------------------------------------------
# POLICY LOADER
# ---------------------------------------------------------------------

def load_policy(school_id: int, term_id: int) -> AssessmentPolicy:
    """
    Load the active assessment policy for a given school and term.
    Raises ValidationError if none found.
    """
    logger.info(f"Loading policy for school_id={school_id}, term_id={term_id}")
    policy = (
        AssessmentPolicy.objects.filter(
            school_id=school_id,
            term_id=term_id,
            is_active=True,
        )
        .only("ca_weight", "exam_weight")
        .first()
    )
    if not policy:
        logger.error(f"No active policy found for school_id={school_id}, term_id={term_id}")
        raise ValidationError("No active assessment policy configured.")
    logger.info(f"Policy loaded: CA={policy.ca_weight}%, EXAM={policy.exam_weight}%")
    return policy


def load_assessment_types(policy: AssessmentPolicy) -> list:
    return list(
        policy.assessment_types.all().only("id", "category", "weight", "max_score", "count")
    )


# ---------------------------------------------------------------------
# AGGREGATION ENGINE
# ---------------------------------------------------------------------

def aggregate_scores(student_ids: list, subject_ids: list, term: AcademicTerm) -> dict:
    """
    Aggregate approved assessment scores per (student_id, subject_id, assessment_type_id).

    Returns:
        {(student_id, subject_id): {assessment_type_id: Decimal(total_score)}}
    """
    logger.info(f"Aggregating scores for {len(student_ids)} students, term={term.id}")

    rows = (
        AssessmentRecord.objects.filter(
            student_id__in=student_ids,
            classroom_subject_id__in=subject_ids,
            period__term=term,
            status=ReviewStatus.APPROVED,
        )
        .values("student_id", "classroom_subject_id", "assessment_type_id")
        .annotate(total_score=Sum("score"))
    )

    data = {}
    for r in rows:
        key = (r["student_id"], r["classroom_subject_id"])
        data.setdefault(key, {})
        data[key][r["assessment_type_id"]] = Decimal(r["total_score"] or 0)

    logger.info(f"Aggregated {len(rows)} rows into {len(data)} student-subject pairs")
    return data


# ---------------------------------------------------------------------
# SCORE ENGINE
# ---------------------------------------------------------------------

def compute_scores(
    stage: str,
    agg: dict,
    student_id: int,
    subject_id: int,
    assessment_types: list,
) -> Tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """
    Compute all score components for a single student/subject pair.

    Stage controls what contributes to total_score:
    - HALF_TERM:   CA only (mid-term progress check, no exam yet)
    - END_OF_TERM: CA + EXAM (final result)

    Returns:
        (ca_total, exam_total, half_term_total, total_score, average_score)
    """
    record = agg.get((student_id, subject_id), {})
    category_totals: Dict[str, Decimal] = {}

    for at in assessment_types:
        raw_score = record.get(at.id, Decimal("0"))
        max_total = Decimal(at.max_score * at.count)
        if max_total == 0:
            continue
        normalized = (raw_score / max_total) * Decimal(str(at.weight))
        category_totals.setdefault(at.category, Decimal("0"))
        category_totals[at.category] += normalized

    ca_total = category_totals.get("CA", Decimal("0"))
    exam_total = category_totals.get("EXAM", Decimal("0"))
    half_term_total = category_totals.get("HALF_TERM", Decimal("0"))

    if stage == SubjectResult.Stage.HALF_TERM:
        total = ca_total
    elif stage == SubjectResult.Stage.END_OF_TERM:
        total = ca_total + exam_total
    else:
        total = sum(category_totals.values(), Decimal("0"))

    total = min(total, Decimal("100"))

    avg = (
        sum(category_totals.values(), Decimal("0")) / Decimal(len(category_totals))
        if category_totals else Decimal("0")
    )

    return ca_total, exam_total, half_term_total, total, avg


# ---------------------------------------------------------------------
# SUBJECT RESULTS (BULK)
# ---------------------------------------------------------------------

@transaction.atomic
def compute_all_subject_results(
    class_group: ClassRoom,
    term: AcademicTerm,
    stage: str = SubjectResult.Stage.END_OF_TERM,
) -> Dict[str, int]:
    """
    Compute and persist subject results for all students in a class.

    - HALF_TERM stage: computes CA scores only, no grade assigned.
    - END_OF_TERM stage: computes CA + exam, assigns grades.

    Existing results for the same (student, subject, term, stage) are updated.
    Results for the other stage are never touched.
    """
    logger.info(f"Computing subject results | class={class_group.id} term={term.id} stage={stage}")

    student_ids = list(
        Student.objects.filter(classroom=class_group).values_list("id", flat=True)
    )
    subject_ids = list(
        Subject.objects.filter(class_rooms=class_group).values_list("id", flat=True)
    )

    if not student_ids or not subject_ids:
        logger.warning(f"No students or subjects found for class_group={class_group.id}")
        return {"created": 0, "updated": 0}

    school_id = class_group.school_id
    policy = load_policy(school_id, term.id)
    scales = load_grade_scales(school_id)
    assessment_types = load_assessment_types(policy)
    agg = aggregate_scores(student_ids, subject_ids, term)

    # Load existing results for this stage only
    existing_results = {
        (r.student_id, r.classroom_subject_id): r
        for r in SubjectResult.objects.filter(
            student_id__in=student_ids,
            classroom_subject_id__in=subject_ids,
            term=term,
            stage=stage,
        ).only(
            "id", "student_id", "classroom_subject_id",
            "total_ca", "exam_score", "half_term_score",
            "total_score", "average_score",
            "grade", "grade_point", "comment",
        )
    }

    is_end_term = stage == SubjectResult.Stage.END_OF_TERM
    payload_fields = [
        "total_ca", "exam_score", "half_term_score",
        "total_score", "average_score",
        "grade", "grade_point", "comment",
    ]

    to_create, to_update = [], []

    # Union of keys from DB and aggregated scores
    all_keys = set(existing_results.keys()) | set(agg.keys())

    for student_id, subject_id in all_keys:
        ca, exam, half, total, avg = compute_scores(
            stage, agg, student_id, subject_id, assessment_types
        )

        grade, point, remark = (
            map_grade(total, scales) if is_end_term
            else (None, None, "Progress assessment")
        )

        payload = {
            "total_ca": ca,
            "exam_score": exam,
            "half_term_score": half,
            "total_score": total,
            "average_score": avg,
            "grade": grade,
            "grade_point": point,
            "comment": remark,
        }

        obj = existing_results.get((student_id, subject_id))
        if obj:
            for field, value in payload.items():
                setattr(obj, field, value)
            to_update.append(obj)
        else:
            to_create.append(
                SubjectResult(
                    student_id=student_id,
                    classroom_subject_id=subject_id,
                    term=term,
                    stage=stage,
                    **payload,
                )
            )

    if to_create:
        SubjectResult.objects.bulk_create(to_create, batch_size=1000)
    if to_update:
        SubjectResult.objects.bulk_update(to_update, fields=payload_fields, batch_size=1000)

    logger.info(f"Subject results done: created={len(to_create)}, updated={len(to_update)}")
    return {"created": len(to_create), "updated": len(to_update)}


# ---------------------------------------------------------------------
# TERM SUMMARY (BULK)
# ---------------------------------------------------------------------

@transaction.atomic
def compute_term_summary(
    class_group: ClassRoom,
    term: AcademicTerm,
    stage: str = SubjectResult.Stage.END_OF_TERM,
) -> List[TermReportSummary]:
    """
    Aggregate SubjectResults into TermReportSummary records and assign class positions.

    Must be called after compute_all_subject_results() for the same stage.
    Summaries for different stages are fully independent — no cross-stage overwriting.
    """
    logger.info(f"Computing term summary | class={class_group.id} term={term.id} stage={stage}")

    # Aggregate from SubjectResult for this stage only
    rows = (
        SubjectResult.objects.filter(
            classroom_subject__class_rooms=class_group,
            term=term,
            stage=stage,
        )
        .values("student_id")
        .annotate(
            total_score=Sum("total_score"),
            total_points=Sum("grade_point"),
            subject_count=Sum(1),
        )
    )

    def to_decimal(value) -> Decimal:
        return Decimal("0") if value is None else Decimal(str(value))

    aggregated = {}
    for r in rows:
        sid = r["student_id"]
        total_score = to_decimal(r.get("total_score"))
        total_points = to_decimal(r.get("total_points"))
        subject_count = r.get("subject_count") or 1
        aggregated[sid] = {
            "total_score": total_score,
            "average_score": total_score / Decimal(subject_count),
            "total_points": total_points,
        }

    student_ids = list(
        Student.objects.filter(classroom=class_group).values_list("id", flat=True)
    )

    # Load existing summaries for this stage only
    existing_summaries = {
        s.student_id: s
        for s in TermReportSummary.objects.filter(
            student_id__in=student_ids,
            class_group=class_group,
            term=term,
            stage=stage,
        ).only(
            "id", "student_id", "total_score",
            "average_score", "total_points", "gpa", "class_position",
        )
    }

    payload_fields = ["total_score", "average_score", "total_points", "gpa"]
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
            "gpa": total_points.quantize(Decimal("0.01")),
        }

        obj = existing_summaries.get(student_id)
        if obj:
            for field, value in payload.items():
                setattr(obj, field, value)
            to_update.append(obj)
            summaries.append(obj)
        else:
            obj = TermReportSummary(
                student_id=student_id,
                class_group=class_group,
                term=term,
                stage=stage,
                **payload,
            )
            to_create.append(obj)
            summaries.append(obj)

    if to_create:
        TermReportSummary.objects.bulk_create(to_create, batch_size=1000)
    if to_update:
        TermReportSummary.objects.bulk_update(to_update, fields=payload_fields, batch_size=1000)

    logger.info(f"Term summaries done: created={len(to_create)}, updated={len(to_update)}")

    _assign_positions(summaries)
    return summaries


# ---------------------------------------------------------------------
# CLASS POSITION ASSIGNMENT
# ---------------------------------------------------------------------

def _assign_positions(summaries: List[TermReportSummary]) -> None:
    """
    Assign class positions ranked by total_points then total_score descending.
    Ties receive the same rank.
    """
    total_students = len(summaries)
    if not total_students:
        return

    logger.info(f"Assigning positions for {total_students} students")

    summaries.sort(key=lambda s: (-s.total_points, -s.total_score))

    last_rank, last_value = 0, None
    for idx, s in enumerate(summaries, start=1):
        current = (s.total_points, s.total_score)
        if current == last_value:
            s.class_position = last_rank
        else:
            s.class_position = idx
            last_rank, last_value = idx, current

    TermReportSummary.objects.bulk_update(summaries, ["class_position"], batch_size=1000)

    logger.info(
        f"Positions assigned | top: student_id={summaries[0].student_id} pos={summaries[0].class_position}"
        f" | last: student_id={summaries[-1].student_id} pos={summaries[-1].class_position}"
    )
