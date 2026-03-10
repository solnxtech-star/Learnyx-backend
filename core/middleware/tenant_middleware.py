from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin

from core.applications.users.models import School
from core.helper.tenants import set_current_school
import contextlib


class CurrentSchoolMiddleware(MiddlewareMixin):
    """
    Detect the current tenant based on subdomain, headers, or request user.
    Sets it in thread-local storage.
    """

    def process_request(self, request: HttpRequest):
        """
        Determine the current tenant (school) and set it in thread-local storage.
        Detection logic:
         1. Subdomain-based: Extract subdomain and match with School.slug.
         2. Authenticated user's school: If user is authenticated, use their associated school.
        """
        school = None

        # Example 1: Subdomain-based
        host = request.get_host()  # e.g., "school1.example.com"
        subdomain = host.split(".")[0]
        with contextlib.suppress(School.DoesNotExist):
            school = School.objects.get(slug=subdomain)

        # Example 2: Authenticated user's school
        if not school and hasattr(request, "user") and request.user.is_authenticated:
            school = getattr(request.user, "school", None)

        set_current_school(school)
        request.current_school = school
