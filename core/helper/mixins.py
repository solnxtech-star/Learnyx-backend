from rest_framework.exceptions import ValidationError

from core.applications.academics.models import AcademicSession
from core.applications.academics.models import AcademicTerm


class CurrentAcademicContextMixin:
    """
    Resolves the current academic session and term.

    This mixin centralizes academic time context to ensure
    consistent behavior across all academic endpoints.

    Usage:
        academic_context = self.get_current_academic_context(school=request.user.school)
        current_session = academic_context["session"]
        current_term = academic_context["term"]
    """

    def get_current_academic_context(self, school=None):
        try:
            # Get the active academic session(s)
            session_qs = AcademicSession.objects.filter(is_active=True)
            # Get the active academic term(s)
            term_qs = AcademicTerm.objects.filter(is_active=True)

            # Optional school scoping (multi-tenant)
            if school is not None:
                session_qs = session_qs.filter(school=school)
                term_qs = term_qs.filter(session__school=school)

            # Return a single session & term
            return {
                "session": session_qs.get(),
                "term": term_qs.get(),
            }

        except AcademicSession.DoesNotExist:
            msg = "Current academic session is not configured."
            raise ValidationError(msg) from None
        except AcademicTerm.DoesNotExist:
            msg = "Current academic term is not configured."
            raise ValidationError(msg) from None
