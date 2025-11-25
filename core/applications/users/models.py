from typing import ClassVar
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from core.helper.models import TimeStampedModel
from core.helper.enums import AdminType, UserRole, Gender, AcademicClass, AdmissionStatus
from .managers import UserManager

import auto_prefetch
import uuid
import secrets



class School(models.Model):
    """Main model for multi-tenant SaaS."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, db_index=True)

    # IMPORTANT: Used for signup by school_code
    school_code = models.CharField(
        max_length=12,
        unique=True,
        editable=False,
        db_index=True,
        help_text=_("Unique auto-generated code used for user onboarding"),
    )

    address = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-generate slug if missing
        if not self.slug:
            self.slug = slugify(self.name)

        # Auto-generate school code if missing
        if not self.school_code:
            self.school_code = self.generate_school_code()

        super().save(*args, **kwargs)

    @staticmethod
    def generate_school_code():
        """Generate a secure unique code like: SCH-84JF9KD2."""
        return "SCH-" + secrets.token_hex(4).upper()


class User(AbstractUser):
    """Custom user model with email login + school assignment."""

    school = models.ForeignKey(
        "users.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users"
    )

    name = models.CharField(_("Full Name"), max_length=255, blank=True)
    email = models.EmailField(_("Email Address"), unique=True)
    phone_number = models.CharField(
        _("Phone Number"), max_length=20, blank=True, null=True
    )

    role = models.CharField(
        _("User Role"),
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.STUDENT,
    )

    is_verified = models.BooleanField(_("Email Verified"), default=False)
    date_joined = models.DateTimeField(_("Date Joined"), auto_now_add=True)
    last_login = models.DateTimeField(_("Last Login"), blank=True, null=True)

    # Remove Django default fields
    username = None
    first_name = None
    last_name = None

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects: ClassVar[UserManager] = UserManager()

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"



class BaseProfile(TimeStampedModel):
    """Abstract base profile for all role-specific extended data."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s_profile",
    )

    @property
    def school(self):
        return self.user.school

    class Meta(auto_prefetch.Model.Meta):
        abstract = True



class AdminProfile(BaseProfile):
    admin_type = models.CharField(
        max_length=50,
        choices=AdminType.choices,
        default=AdminType.OTHER
    )
    position = models.CharField(_("Position"), max_length=100, blank=True, null=True)
    school_name = models.CharField(_("School Name"), max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Admin ({self.admin_type}): {self.user.name or self.user.email}"




class TeacherProfile(BaseProfile):
    staff_id = models.CharField(_("Staff ID"), max_length=50, unique=True)
    qualification = models.CharField(max_length=100, blank=True, null=True)
    specialization = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Teacher: {self.user.name or self.user.email}"


class StudentProfile(BaseProfile):
    student_id = models.CharField(
        _("Student ID"), max_length=50, unique=True, blank=True, editable=False
    )
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    current_class = models.CharField(max_length=20, choices=AcademicClass.choices, blank=True, null=True)
    admission_date = models.DateField(blank=True, null=True)
    guardian_name = models.CharField(max_length=100, blank=True, null=True)
    guardian_phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=AdmissionStatus.choices, default=AdmissionStatus.PENDING)
    approved_by = models.CharField(max_length=100, blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.student_id:
            self.student_id = f"STD-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Student: {self.user.name or self.user.email}"


class ParentProfile(BaseProfile):
    occupation = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return f"Parent: {self.user.name or self.user.email}"
