# core/results/services.py
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Avg, Count
from django.core.exceptions import ValidationError

from core.applications.accessments.models import (
    AssessmentPolicy,
    AssessmentRecord,
    SubjectResult,
    TermReportSummary,
    GradeScale,
    AcademicTerm,
    AssessmentType,
)
from core.applications.academics.models import ClassroomSubject, ClassGroup
from core.applications.users.models import Student


def _map_grade_and_point(school, score):
    """
    Map a numeric score to (grade, grade_point, remark) using GradeScale for the given school.
    Returns a tuple (grade, point, remark) or (None, None, None) if not found.
    """
    # Find first matching scale, ordered by highest score first
    qs = GradeScale.objects.filter(
        school=school,
        is_active=True
    ).order_by('-max_score', 'order')

    for scale in qs:
        if scale.min_score <= score <= scale.max_score:
            return scale.grade, float(scale.point), scale.remark
    return None, None, None


@transaction.atomic
def compute_subject_result(student, classroom_subject, term, *, recalc=False):
    """
    Compute and persist SubjectResult for the given student/classroom_subject/term.
    Enhanced to handle different term types (Half Term vs End of Term).
    """
    school = classroom_subject.school

    # Find active policy for school + term
    policy = AssessmentPolicy.objects.filter(
        school=school,
        term=term,
        is_active=True
    ).first()

    if not policy:
        raise ValidationError("No active assessment policy for school/term.")

    # Initialize scores based on term type
    total_ca = 0.0
    exam_score = 0.0
    half_term_score = 0.0
    total_score = 0.0

    # Process different assessment types based on categories
    for atype in policy.assessment_types.all().order_by('order'):
        # Fetch student's scores for this assessment type and class_subject
        records = AssessmentRecord.objects.filter(
            student=student,
            classroom_subject=classroom_subject,
            assessment_type=atype
        )

        if not records.exists():
            if atype.is_optional:
                continue  # Skip optional assessments with no records
            else:
                # Treat missing as zero for required assessments
                avg_score = 0.0
        else:
            # Calculate average score for this assessment type
            total_obtained = sum([r.score or 0 for r in records])
            avg_score = total_obtained / len(records)

        # Categorize scores based on assessment type category
        if atype.category == "EXAM":
            exam_score = avg_score
        elif atype.category == "HALF_TERM":
            half_term_score = avg_score
        elif atype.category == "CA":
            total_ca += avg_score * (atype.weight / 100)  # Apply weight
        else:
            # For other types, add to CA with weight
            total_ca += avg_score * (atype.weight / 100)

    # Calculate total score based on term type
    if term.term_type == "END_TERM":
        # End of Term: CA (40%) + Exam (60%)
        ca_percentage = (total_ca / policy.ca_weight) * policy.ca_weight if total_ca else 0
        exam_percentage = (exam_score / 100) * policy.exam_weight if exam_score else 0
        total_score = ca_percentage + exam_percentage

    elif term.term_type == "HALF_TERM":
        # Half Term: CA + Half Term Exam
        total_score = total_ca + (half_term_score or 0)

    else:
        # Full Term or default
        total_score = total_ca + exam_score

    # Ensure total score doesn't exceed 100
    total_score = min(total_score, 100.0)

    # Grade mapping
    grade, grade_point, remark = _map_grade_and_point(school, total_score)

    # Calculate average for half-term reports
    average_score = None
    if term.term_type == "HALF_TERM":
        # For half-term, average might be calculated differently
        # This could be (total_ca + half_term_score) / 2 or other logic
        count = 2 if half_term_score else 1
        average_score = total_score / count

    # Get target grade if exists
    target_grade_obj = student.target_grades.filter(
        subject=classroom_subject.subject,
        term=term
    ).first()

    target_grade = target_grade_obj.target_grade if target_grade_obj else None
    target_point = target_grade_obj.target_point if target_grade_obj else None

    # Upsert SubjectResult
    subject_result, created = SubjectResult.objects.update_or_create(
        student=student,
        classroom_subject=classroom_subject,
        term=term,
        defaults={
            "total_ca": total_ca,
            "exam_score": exam_score,
            "half_term_score": half_term_score if half_term_score else None,
            "total_score": total_score,
            "average_score": average_score,
            "grade": grade,
            "grade_point": Decimal(str(grade_point)) if grade_point else None,
            "remark": remark or "",
            "target_grade": target_grade,
            "target_point": Decimal(str(target_point)) if target_point else None,
        }
    )

    # Update target achievement status
    if target_grade_obj and grade_point:
        target_grade_obj.check_achievement(grade, grade_point)

    return subject_result


@transaction.atomic
def compute_term_summary_for_class_and_term(class_group: ClassGroup, term: AcademicTerm):
    """
    Compute TermReportSummary for every student in a class_group for the given term.
    Enhanced to handle target comparisons and different term types.
    """
    students = Student.objects.filter(class_group=class_group)

    summaries = []
    for student in students:
        # Aggregate subject results for student within the class
        sr_qs = SubjectResult.objects.filter(
            student=student,
            term=term,
            classroom_subject__class_group=class_group
        ).exclude(total_score__isnull=True)

        # Calculate academic metrics
        total_score = sr_qs.aggregate(total=Sum('total_score'))['total'] or 0.0
        subject_count = sr_qs.count() or 1
        average_score = float(total_score) / float(subject_count)

        # Calculate total points and GPA
        valid_results = sr_qs.exclude(grade_point__isnull=True)
        total_points = valid_results.aggregate(total=Sum('grade_point'))['total'] or 0.0
        gpa = float(total_points) / valid_results.count() if valid_results.count() > 0 else 0.0

        # Calculate target metrics
        target_grades = student.target_grades.filter(term=term)
        target_total_points = target_grades.aggregate(total=Sum('target_point'))['total'] or 0.0
        target_gpa = target_total_points / target_grades.count() if target_grades.count() > 0 else 0.0

        # Get or create term report summary
        summary, created = TermReportSummary.objects.update_or_create(
            student=student,
            term=term,
            class_group=class_group,
            defaults={
                "total_score": total_score,
                "average_score": average_score,
                "total_points": total_points,
                "gpa": round(gpa, 2),
                "target_total_points": target_total_points,
                "target_gpa": round(target_gpa, 2),
            }
        )
        summaries.append(summary)

    # Calculate class positions based on total_points (primary) and total_score (secondary)
    sorted_summaries = sorted(
        summaries,
        key=lambda s: (-s.total_points, -s.total_score)
    )

    # Assign class_position (1-based with ties)
    position = 1
    skip_count = 0
    last_pts = None
    last_score = None

    for idx, summary in enumerate(sorted_summaries, start=1):
        current_pts = summary.total_points
        current_score = summary.total_score

        if last_pts is not None and (current_pts, current_score) == (last_pts, last_score):
            # Same rank as previous student
            summary.class_position = position
            skip_count += 1
        else:
            # New rank
            position = idx
            summary.class_position = position
            skip_count = 0

        summary.save(update_fields=["class_position"])
        last_pts = current_pts
        last_score = current_score

    return sorted_summaries


@transaction.atomic
def compute_all_subjects_and_summary_for_term(term: AcademicTerm, class_group: ClassGroup = None):
    """
    Convenience function to compute SubjectResult for all students/classroom_subjects
    in a class_group for the term, then compute TermReportSummary and ranking.
    """
    if not class_group:
        raise ValueError("Must provide class_group to compute summaries for.")

    classroom_subjects = ClassroomSubject.objects.filter(class_group=class_group)

    for cs in classroom_subjects:
        students = cs.students.all()
        for student in students:
            compute_subject_result(student, cs, term, recalc=True)

    return compute_term_summary_for_class_and_term(class_group, term)


def generate_end_of_term_report_data(student, term):
    """
    Generate data structure for End of Term reports (like first image)
    """
    subject_results = SubjectResult.objects.filter(
        student=student,
        term=term
    ).select_related('classroom_subject', 'classroom_subject__subject')

    report_data = {
        'student': student,
        'term': term,
        'subjects': [],
        'summary': None
    }

    for sr in subject_results:
        # Get teacher comments
        comments = sr.teacher_comments.filter(is_visible_to_parents=True)
        general_comment = comments.filter(comment_type="GENERAL").first()

        subject_info = {
            'subject': sr.classroom_subject.subject.name,
            'ca_score': sr.total_ca,
            'exam_score': sr.exam_score,
            'total_score': sr.total_score,
            'grade': sr.grade,
            'point': sr.grade_point,
            'comment': general_comment.comment if general_comment else sr.remark,
            'target_grade': sr.target_grade,
            'target_point': sr.target_point,
        }
        report_data['subjects'].append(subject_info)

    # Get term summary
    report_data['summary'] = TermReportSummary.objects.filter(
        student=student,
        term=term
    ).first()

    return report_data


def generate_half_term_report_data(student, term):
    """
    Generate data structure for Half Term reports (like second image)
    """
    subject_results = SubjectResult.objects.filter(
        student=student,
        term=term
    ).select_related('classroom_subject', 'classroom_subject__subject')

    report_data = {
        'student': student,
        'term': term,
        'subjects': [],
        'summary': None,
        'grading_key': None
    }

    for sr in subject_results:
        subject_info = {
            'subject': sr.classroom_subject.subject.name,
            'ca_score': sr.total_ca,
            'half_term_score': sr.half_term_score,
            'total_score': sr.total_score,
            'average_score': sr.average_score,
            'point': sr.grade_point,
            'grade': sr.grade,
            'target_point': sr.target_point,
            'target_grade': sr.target_grade,
        }
        report_data['subjects'].append(subject_info)

    # Get term summary
    report_data['summary'] = TermReportSummary.objects.filter(
        student=student,
        term=term
    ).first()

    # Get grading scale for the school
    report_data['grading_key'] = GradeScale.objects.filter(
        school=student.school,
        is_active=True
    ).order_by('-max_score')

    return report_data
