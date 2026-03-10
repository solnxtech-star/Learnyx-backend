from typing import TYPE_CHECKING

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models

if TYPE_CHECKING:
    from .models import User  # noqa: F401


class UserManager(DjangoUserManager["User"]):
    """Custom manager for the User model."""

    def _create_user(self, email: str, password: str | None, **extra_fields):
        """
        Create and save a User with the given email and password.
        """

        if not email:
            raise ValueError("The given email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        """Create and save a regular User with the given email and password."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            msg = "Superuser must have is_staff=True."
            raise ValueError(msg)
        if extra_fields.get("is_superuser") is not True:
            msg = "Superuser must have is_superuser=True."
            raise ValueError(msg)
        return self._create_user(email, password, **extra_fields)


# Tenant-aware QuerySet
class TenantQuerySet(models.QuerySet):
    def for_school(self, school):
        """Filter queryset for a specific tenant."""
        return self.filter(school=school)

    def active(self):
        if hasattr(self.model, "is_active"):
            return self.filter(is_active=True)
        return self


# Tenant-aware manager
class TenantManager(models.Manager):
    """Custom manager that uses TenantQuerySet for tenant-aware queries."""
    def __init__(self, *args, **kwargs):
        self.current_school = kwargs.pop("current_school", None)
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        qs = TenantQuerySet(self.model, using=self._db)
        if self.current_school:
            qs = qs.for_school(self.current_school)
        return qs

    def for_school(self, school):
        return self.get_queryset().for_school(school)

class SchoolManager(models.Manager):
    """Custom manager for tenant-aware School queries."""

    def active(self):
        """Return only active schools."""
        return self.get_queryset().filter(is_active=True)

    def by_code(self, code):
        """Return school by unique school_code."""
        return self.get_queryset().filter(school_code=code).first()
