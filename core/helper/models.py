import logging
import uuid
from typing import TYPE_CHECKING
from typing import Any

import auto_prefetch
from django import forms
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from model_utils import FieldTracker

from core.applications.users.managers import TenantManager
from core.helper.tenants import get_current_db_alias
from core.helper.tenants import get_current_school

if TYPE_CHECKING:
    from core.applications.users.models import School

logger = logging.getLogger(__name__)

def generate_uuid() -> str:
    """Generate a unique 32-character hexadecimal UUID string."""
    return uuid.uuid4().hex


class ChoiceArrayField(ArrayField):
    """
    Custom ArrayField that supports multiple-choice form rendering.

    Example:
        tags = ChoiceArrayField(
            base_field=models.CharField(max_length=50, choices=TAG_CHOICES)
        )
    """

    def formfield(self, **kwargs: Any) -> forms.Field:
        defaults = {
            "form_class": forms.TypedMultipleChoiceField,
            "choices": self.base_field.choices,
            "coerce": self.base_field.to_python,
            "widget": forms.CheckboxSelectMultiple,
        }
        defaults.update(kwargs)
        return super().formfield(**defaults)


class VisibleManager(auto_prefetch.Manager):
    """Manager that filters for visible=True objects."""

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(visible=True)


class TimeStampedModel(auto_prefetch.Model):
    """
    Abstract base model providing UUID primary key,
    visibility flag, and automatic timestamp fields.
    """

    id = models.CharField(
        primary_key=True,
        default=generate_uuid,
        max_length=32,
        editable=False,
        unique=True,
    )
    visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Managers
    objects = auto_prefetch.Manager()
    visible_items = VisibleManager()

    class Meta(auto_prefetch.Model.Meta):
        abstract = True
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return str(self.id)


class TitleModel(TimeStampedModel):
    """Abstract model with a title field and alphabetical ordering."""

    title = models.CharField(max_length=100, blank=True)

    class Meta(TimeStampedModel.Meta):
        abstract = True
        ordering = ["title", "-created_at"]

    def __str__(self) -> str:
        return self.title or str(self.id)


class NamedModel(TimeStampedModel):
    """Abstract model with a name field and change tracking."""

    name = models.CharField(max_length=255, blank=True)
    tracker = FieldTracker()

    class Meta(TimeStampedModel.Meta):
        abstract = True

    def __str__(self) -> str:
        return self.name or str(self.id)


class UserTrackedModel(TimeStampedModel):
    """Abstract model that records who created and last updated an object."""

    created_by = auto_prefetch.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="%(class)s_created_by",
    )
    updated_by = auto_prefetch.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="%(class)s_updated_by",
    )
    tracker = FieldTracker()

    class Meta(TimeStampedModel.Meta):
        abstract = True

    def __str__(self) -> str:
        return str(self.id)


class AccountTrackedModel(TimeStampedModel):
    """
    Abstract model variant that associates creation with an Account
    instead of a User. Useful for admin-level models.
    """

    created_by = auto_prefetch.ForeignKey(
        "users.Account",
        on_delete=models.CASCADE,
        related_name="%(class)s_created_by",
    )

    class Meta(TimeStampedModel.Meta):
        abstract = True


class TenantAwareModel(TimeStampedModel):

    school = models.ForeignKey(
        "users.School",
        on_delete=models.CASCADE,
        db_index=True,
        related_name="%(class)ss",
        help_text=_("The school (tenant) this record belongs to."),
    )

    objects = TenantManager()

    class Meta:
        abstract = True

    # ------------------------------------------------------------------
    # Save — auto-assign + validate school before every write
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        """
        Override save to:
        1. Auto-assign school from thread-local if not set
        2. Run full validation before write
        3. Log tenant context for debugging
        """
        self._assign_school_from_context()
        self.full_clean()  # triggers clean() below
        logger.debug(
            "Saving %s → school=%s | db=%s",
            self.__class__.__name__,
            self.school_id,
            get_current_db_alias(),
        )
        super().save(*args, **kwargs)

    def _assign_school_from_context(self) -> None:
        """
        Auto-assign school from thread-local context if not already set.
        This means views and services never need to manually set school=...
        on every model they create.

        Raises ValidationError if school cannot be determined —
        this is always a programming error, not a user error.
        """
        if self.school_id:
            # Already set — nothing to do
            return

        school = get_current_school()
        if school is not None:
            self.school = school
            logger.debug(
                "Auto-assigned school '%s' to %s from thread-local context.",
                school,
                self.__class__.__name__,
            )
            return

        raise ValidationError(
            _(
                "%(model)s cannot be saved without a school context. "
                "Ensure CurrentSchoolMiddleware is active or pass "
                "school explicitly."
            ),
            params={"model": self.__class__.__name__},
        )

    # ------------------------------------------------------------------
    # Validation — cross-tenant consistency checks
    # ------------------------------------------------------------------

    def clean(self):
        """
        Validate tenant consistency.

        Checks:
        1. school must be set (defence in depth after _assign_school_from_context)
        2. school must be active — no writes to deactivated tenants
        3. Any related TenantAwareModel fields must belong to the same school
           to prevent cross-tenant data corruption
        """
        super().clean()
        self._validate_school_set()
        self._validate_school_active()
        self._validate_related_tenant_fields()

    def _validate_school_set(self) -> None:
        """School must be set before any validation proceeds."""
        if not self.school_id:
            raise ValidationError(
                {"school": _("A school must be assigned to this record.")}
            )

    def _validate_school_active(self) -> None:
        """Prevent writes to deactivated school tenants."""
        try:
            school = self.school
        except Exception:
            return  # school not loaded yet — skip, caught by _validate_school_set

        if not school.is_active:
            raise ValidationError(
                _(
                    "Cannot write to '%(school)s' — "
                    "this school's account is deactivated."
                ),
                params={"school": school.name},
            )

    def _validate_related_tenant_fields(self) -> None:
        """
        Check all ForeignKey fields on this model.
        If the related model is also a TenantAwareModel, it must
        belong to the same school as self.

        This prevents cross-tenant corruption like:
            StudentContact(school=SchoolA, student=<student from SchoolB>)

        Only runs when school_id is set (after _validate_school_set passes).
        """
        if not self.school_id:
            return

        for field in self._meta.get_fields():
            # Only check ForeignKey fields (not reverse relations)
            if not isinstance(field, models.ForeignKey):
                continue

            # Skip the school FK itself
            if field.name == "school":
                continue

            # Skip fields pointing to master models (User, School etc.)
            # These live on default DB and are cross-tenant by design
            related_model = field.related_model
            if not related_model:
                continue
            if not issubclass(related_model, TenantAwareModel):
                continue

            # Get the related object's value
            related_id = getattr(self, f"{field.attname}", None)
            if not related_id:
                continue  # nullable FK not set — skip

            try:
                related_obj = getattr(self, field.name)
            except related_model.DoesNotExist:
                continue

            # The critical check
            if related_obj.school_id != self.school_id:
                raise ValidationError(
                    _(
                        "%(field)s belongs to a different school. "
                        "Cross-tenant relations are not permitted."
                    ),
                    params={"field": field.verbose_name or field.name},
                )
                logger.error(
                    "Cross-tenant relation detected: "
                    "%s.%s (school=%s) → %s (school=%s)",
                    self.__class__.__name__,
                    field.name,
                    self.school_id,
                    related_model.__name__,
                    related_obj.school_id,
                )

    # ------------------------------------------------------------------
    # Classmethods — querying helpers
    # ------------------------------------------------------------------

    @classmethod
    def for_school(cls, school):
        """
        Explicit school-scoped queryset.
        Use when you need data for a specific school regardless
        of the current thread-local context.

        Example:
            StudentContact.for_school(school).filter(is_primary=True)
        """
        return cls.objects.for_school(school)

    @classmethod
    def unscoped(cls):
        """
        Unscoped queryset — returns all rows across all tenants.
        Use ONLY for superadmin / cross-tenant reporting.
        Never expose this to tenant-level views or APIs.

        Example:
            StudentContact.unscoped().filter(name="John")
        """
        return cls.objects.unscoped()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def tenant_db(self) -> str:
        """
        The database alias this record lives on.
        Convenience property for debugging and logging.
        """
        return self._state.db or get_current_db_alias()
