# core/applications/users/managers.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models

from core.helper.tenants import get_current_db_alias
from core.helper.tenants import get_current_school

if TYPE_CHECKING:
    from core.applications.users.models import School  # noqa: F401
    from core.applications.users.models import User  # noqa: F401

logger = logging.getLogger(__name__)


# ==============================================================================
# User Manager
# ==============================================================================

class UserManager(DjangoUserManager["User"]):
    """
    Custom manager for the User model.
    User always lives in the master/default database.
    No tenant scoping needed — handled by the router.
    """

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("The given email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self, email: str, password: str | None = None, **extra_fields
    ):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


# ==============================================================================
# School Manager
# ==============================================================================

class SchoolQuerySet(models.QuerySet):
    """QuerySet for School model — always on master database."""

    def active(self):
        return self.filter(is_active=True)

    def isolated(self):
        """Schools on their own dedicated database."""
        return self.filter(db_tier="isolated")

    def shared(self):
        """Schools on the shared default database."""
        return self.filter(db_tier="shared")


class SchoolManager(models.Manager):
    """
    Manager for the School model.
    Always queries the master/default database.
    School records are never tenant-scoped — they are platform-level data.
    """

    def get_queryset(self):
        # School always lives on default — explicit using() for clarity
        return SchoolQuerySet(self.model, using="default")

    def active(self):
        return self.get_queryset().active()

    def by_code(self, code: str) -> School | None:
        """
        Look up a school by its onboarding code.
        Raises School.DoesNotExist on miss so callers handle it explicitly.
        Use by_code_safe() where None is an acceptable outcome.
        """
        return self.get_queryset().get(
            school_code=code.upper().strip(),
            is_active=True,
        )

    def by_code_safe(self, code: str) -> School | None:
        """Return school by code or None — never raises."""
        try:
            return self.by_code(code)
        except self.model.DoesNotExist:
            return None

    def by_slug(self, slug: str) -> School | None:
        """Look up active school by slug — used by middleware."""
        try:
            return self.get_queryset().get(slug=slug, is_active=True)
        except self.model.DoesNotExist:
            return None

    def by_custom_domain(self, domain: str) -> School | None:
        """Look up active school by custom domain — used by middleware."""
        try:
            return self.get_queryset().get(
                custom_domain=domain,
                is_active=True,
            )
        except self.model.DoesNotExist:
            return None


# ==============================================================================
# Tenant QuerySet — for TenantAwareModel subclasses
# (StudentEnrollment, StudentContact, etc.)
# These models have a direct school FK
# ==============================================================================

class TenantQuerySet(models.QuerySet):
    """
    QuerySet for models that extend TenantAwareModel.
    These have a direct `school` FK column.
    """

    def for_school(self, school):
        """Explicitly scope to a specific school."""
        return self.filter(school=school)

    def active(self):
        """Filter by is_active if the model has it."""
        if hasattr(self.model, "is_active"):
            return self.filter(is_active=True)
        return self

    def unscoped(self):
        """
        Return the full unfiltered queryset.
        Use only in superadmin / cross-tenant operations.
        """
        return self


class TenantManager(models.Manager):
    """
    Manager for TenantAwareModel subclasses.
    These models have a direct `school` FK.

    Auto-scoping behaviour:
        - Reads current school from thread-local (set by middleware)
        - Routes to correct database via db_alias (set by router)
        - Falls back to unscoped if no tenant context exists
          (management commands, tests, superadmin)
    """

    def get_queryset(self):
        # Router handles database selection via thread-local db_alias
        # We just need to scope by school FK here
        qs = TenantQuerySet(self.model, using=self._db)
        school = get_current_school()

        if school is not None:
            qs = qs.for_school(school)
            logger.debug(
                "TenantManager scoped → model=%s | school=%s | db=%s",
                self.model._meta.label,
                school,
                get_current_db_alias(),
            )

        return qs

    def for_school(self, school):
        """
        Explicit school scoping — bypasses thread-local.
        Use when you need to query a specific school's data
        regardless of the current request context.
        """
        return TenantQuerySet(self.model, using=self._db).for_school(school)

    def unscoped(self):
        """
        Return completely unscoped queryset.
        Use only for superadmin cross-tenant operations.
        Never expose this to tenant-level views.
        """
        return TenantQuerySet(self.model, using=self._db)


# ==============================================================================
# Profile Tenant QuerySet — for BaseProfile subclasses
# (StudentProfile, TeacherProfile, AdminProfile, ParentProfile)
# These models reach school via user.school — no direct school FK
# ==============================================================================

class ProfileTenantQuerySet(models.QuerySet):
    """
    QuerySet for profile models that extend BaseProfile.
    These models have NO direct school FK.
    School is accessed via user__school.
    """

    def for_school(self, school):
        """Scope to a specific school via user relation."""
        return self.filter(user__school=school)

    def active(self):
        """
        Filter by admission status if the model has it.
        Profiles use AdmissionStatus not is_active.
        """
        if hasattr(self.model, "status"):
            from core.helper.enums import AdmissionStatus
            return self.filter(status=AdmissionStatus.APPROVED)
        return self

    def pending(self):
        """Return profiles awaiting approval."""
        if hasattr(self.model, "status"):
            from core.helper.enums import AdmissionStatus
            return self.filter(status=AdmissionStatus.PENDING)
        return self

    def unscoped(self):
        """Full unfiltered queryset — superadmin only."""
        return self


class ProfileTenantManager(models.Manager):
    """
    Manager for BaseProfile subclasses.
    (StudentProfile, TeacherProfile, AdminProfile, ParentProfile)

    Differences from TenantManager:
        - Filters via user__school instead of school directly
        - active() checks AdmissionStatus not is_active
        - pending() helper for approval workflows

    Auto-scoping behaviour is identical to TenantManager:
        - Reads current school from thread-local
        - Router handles correct database via db_alias
    """

    def get_queryset(self):
        qs = ProfileTenantQuerySet(self.model, using=self._db)
        school = get_current_school()

        if school is not None:
            qs = qs.for_school(school)
            logger.debug(
                "ProfileTenantManager scoped → model=%s | school=%s | db=%s",
                self.model._meta.label,
                school,
                get_current_db_alias(),
            )

        return qs

    def for_school(self, school):
        """Explicit school scoping — bypasses thread-local."""
        return ProfileTenantQuerySet(
            self.model, using=self._db
        ).for_school(school)

    def unscoped(self):
        """Unscoped queryset — superadmin only."""
        return ProfileTenantQuerySet(self.model, using=self._db)
