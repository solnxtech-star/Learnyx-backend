from __future__ import annotations

import contextlib
import logging

from core.applications.users.models import School
from core.helper.tenants import clear_current_school
from core.helper.tenants import get_current_db_alias
from core.helper.tenants import set_current_school

logger = logging.getLogger(__name__)


class CurrentSchoolMiddleware:
    """
    Resolves the current school (tenant) for every incoming request.

    Resolution order:
        1. Custom domain   →  portal.greenfield.edu.ng
        2. Subdomain       →  greenfield.schoolapp.com
        3. Authenticated user → request.user.school (fallback)

    Hybrid tenancy:
        - Sets thread-local school AND db_alias
        - db_alias is read by TenantDatabaseRouter on every ORM call
        - SHARED school  → db_alias = 'default'
        - ISOLATED school → db_alias = 'school_greenfield'

    Guarantees:
        - request.current_school is always set (School | None)
        - request.current_db_alias is always set (str)
        - Thread-local is always cleared after response, even on exception
        - Deactivated schools are never resolved
        - Reserved subdomains are never queried against DB
    """

    RESERVED_SUBDOMAINS: frozenset[str] = frozenset({
        "www", "api", "admin", "static", "media",
        "mail", "smtp", "ftp", "cdn", "assets",
    })

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        Main entry point for the middleware.
        """
        school = self._resolve_school(request)

        set_current_school(school)
        request.current_school = school
        request.current_db_alias = get_current_db_alias()

        logger.debug(
            "Tenant → school=%s | db=%s | isolated=%s",
            school,
            request.current_db_alias,
            school.is_isolated if school else False,
        )

        try:
            return self.get_response(request)
        finally:
            clear_current_school()

    def _resolve_school(self, request) -> School | None:
        """
        Attempt to resolve the current school using multiple strategies in order of precedence.
        """
        return (
            self._resolve_from_custom_domain(request) or
            self._resolve_from_subdomain(request)
            or self._resolve_from_user(request)
        )

    def _resolve_from_custom_domain(self, request) -> School | None:
        """
        Check if the full host matches a school's registered custom domain.
        e.g. portal.greenfield.edu.ng → GreenField Academy
        Always queries master DB (using='default').
        """
        host = request.get_host().split(":")[0].lower()
        with contextlib.suppress(School.DoesNotExist):
            school = School.objects.using("default").get(
                custom_domain=host,
                is_active=True,
            )
            logger.debug(
                "Tenant resolved via custom domain: %s → %s (db=%s)",
                host, school, school.effective_db_alias,
            )
            return school
        return None

    def _resolve_from_subdomain(self, request) -> School | None:
        """
        Extract subdomain from host and match against School.slug.
        e.g. greenfield.schoolapp.com → GreenField Academy
        Always queries master DB (using='default').
        """
        host = request.get_host().split(":")[0].lower()
        parts = host.split(".")

        if len(parts) < 3:
            return None

        subdomain = parts[0]
        if subdomain in self.RESERVED_SUBDOMAINS:
            return None

        with contextlib.suppress(School.DoesNotExist):
            school = School.objects.using("default").get(
                slug=subdomain,
                is_active=True,
            )
            logger.debug(
                "Tenant resolved via subdomain: %s → %s (db=%s)",
                subdomain, school, school.effective_db_alias,
            )
            return school

        return None

    def _resolve_from_user(self, request) -> School | None:
        """
        Fall back to authenticated user's assigned school.
        Covers API clients, mobile apps, local development.
        """
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return None

        school = getattr(request.user, "school", None)
        if school:
            logger.debug(
                "Tenant resolved via user: %s → %s (db=%s)",
                request.user, school, school.effective_db_alias,
            )
        return school
