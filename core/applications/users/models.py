from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from django.conf import settings
from core.helper.models import TimeStampedModel
from core.helper.enums import UserRole, Gender, AcademicClass, AdmissionStatus
from .managers import UserManager

import auto_prefetch
import uuid


class User(AbstractUser):
    """
    Custom user model for Learnxy Backend.

    This model replaces Django's default username-based authentication
    with an email-based system and supports multiple user roles (admin, teacher, student, parent).
    """

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

    # Remove username fields since email is now unique identifier
    username = None  # type: ignore[assignment]
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects: ClassVar[UserManager] = UserManager()

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"

    def get_absolute_url(self):
        """Return canonical URL for user detail view."""
        return reverse("users:detail", kwargs={"pk": self.pk})

    # Role-based convenience checks
    @property
    def is_admin(self):
        return self.role == UserRole.ADMIN

    @property
    def is_teacher(self):
        return self.role == UserRole.TEACHER

    @property
    def is_student(self):
        return self.role == UserRole.STUDENT

    @property
    def is_parent(self):
        return self.role == UserRole.PARENT


class BaseProfile(TimeStampedModel):
    """Abstract base model for all user role profiles."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s_profile",
    )

    class Meta(auto_prefetch.Model.Meta):
        abstract = True


class AdminProfile(BaseProfile):
    """Extended data for administrators."""

    position = models.CharField(_("Position"), max_length=100, blank=True, null=True)
    school_name = models.CharField(
        _("School Name"), max_length=255, blank=True, null=True
    )

    def __str__(self):
        return f"Admin: {self.user.name or self.user.email}"


class TeacherProfile(BaseProfile):
    """Extended data for teachers."""

    staff_id = models.CharField(_("Staff ID"), max_length=50, unique=True)
    qualification = models.CharField(
        _("Qualification"), max_length=100, blank=True, null=True
    )
    specialization = models.CharField(
        _("Subject Specialization"), max_length=100, blank=True, null=True
    )
    department = models.CharField(
        _("Department"), max_length=100, blank=True, null=True
    )

    def __str__(self):
        return f"Teacher: {self.user.name or self.user.email}"


class StudentProfile(BaseProfile):
    """Extended data for students, including admission workflow."""

    student_id = models.CharField(
        _("Student ID"), max_length=50, unique=True, blank=True,
        editable=False
    )
    gender = models.CharField(
        _("Gender"), max_length=10, choices=Gender.choices, blank=True
    )
    current_class = models.CharField(
        _("Current Class"),
        max_length=20,
        choices=AcademicClass.choices,
        blank=True,
        null=True,
    )
    admission_date = models.DateField(_("Admission Date"), blank=True, null=True)
    guardian_name = models.CharField(
        _("Guardian Name"), max_length=100, blank=True, null=True
    )
    guardian_phone = models.CharField(
        _("Guardian Phone"), max_length=20, blank=True, null=True
    )
    address = models.CharField(_("Home Address"), max_length=255, blank=True, null=True)
    status = models.CharField(
        _("Admission Status"),
        max_length=20,
        choices=AdmissionStatus.choices,
        default=AdmissionStatus.PENDING,
    )
    approved_by = models.CharField(
        _("Approved By"), max_length=100, blank=True, null=True
    )

    def __str__(self):
        return f"Student: {self.user.name or self.user.email} ({self.current_class or 'Unassigned'})"


    def save(self, *args, **kwargs):
        if not self.student_id:
            self.student_id = f"STD-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class ParentProfile(BaseProfile):
    """Extended data for parents."""

    occupation = models.CharField(
        _("Occupation"), max_length=100, blank=True, null=True
    )
    address = models.CharField(_("Home Address"), max_length=255, blank=True, null=True)
    phone_number = models.CharField(
        _("Phone Number"), max_length=20, blank=True, null=True
    )

    def __str__(self):
        return f"Parent: {self.user.name or self.user.email}"
