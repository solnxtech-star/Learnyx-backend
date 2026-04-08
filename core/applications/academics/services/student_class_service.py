from django.core.exceptions import ValidationError


def get_student_active_classroom(student):
    """
    Return the active classroom for a student.

    Raises:
        ValidationError: If no active classroom assignment exists.
    """
    assignment = (
        student.class_assignments
        .filter(is_active=True)
        .select_related("classroom")
        .first()
    )

    if not assignment:
        student_name = getattr(student.user, "name", "Student")
        raise ValidationError(
            f"{student_name} is not assigned to any active classroom."
        )

    return assignment.classroom


def get_term_from_assessment(assessment_type):
    """
    Resolve the academic term from an assessment type.

    Expected relationship:
        AssessmentType → AssessmentPolicy → AcademicTerm

    Raises:
        ValidationError: If the relationship is broken.
    """
    policy = getattr(assessment_type, "policy", None)

    if not policy:
        raise ValidationError(
            "Assessment type is not linked to any assessment policy."
        )

    term = getattr(policy, "term", None)

    if not term:
        raise ValidationError(
            "Assessment policy is not linked to any academic term."
        )

    return term
