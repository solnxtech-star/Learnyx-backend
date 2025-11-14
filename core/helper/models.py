import uuid
from typing import Any

import auto_prefetch
from django import forms
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import QuerySet
from model_utils import FieldTracker



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
