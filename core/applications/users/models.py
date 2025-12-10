import secrets
import uuid
from typing import ClassVar

import auto_prefetch
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from core.helper.enums import AcademicClass
from core.helper.enums import AdminType
from core.helper.enums import AdmissionStatus
from core.helper.enums import Gender
from core.helper.enums import UserRole
from core.helper.models import TimeStampedModel

from .managers import UserManager


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
        related_name="users",
    )

    name = models.CharField(_("Full Name"), max_length=255, blank=True)
    email = models.EmailField(_("Email Address"), unique=True)
    phone_number = models.CharField(
        _("Phone Number"),
        max_length=20,
        blank=True,
        null=True,
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
    """
    Abstract base profile shared by all role-specific profile models.

    This includes:
    - A one-to-one relation with the User model
    - Multi-tenancy support (profile.school references user.school)
    - Approval workflow fields (status, approved_by)
    """

    status = models.CharField(
        max_length=20,
        choices=AdmissionStatus.choices,
        default=AdmissionStatus.PENDING,
        help_text=_("Approval status for this profile."),
    )

    approved_by = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text=_("Email of the admin who approved or rejected this profile."),
    )

    @property
    def school(self):
        """Return the school this profile belongs to (from user)."""
        return self.user.school

    class Meta(auto_prefetch.Model.Meta):
        abstract = True


class AdminProfile(BaseProfile):
    """
    Extended profile for admin users within a school.

    Includes:
    - Admin type (School Owner, Principal, etc.)
    - Optional organizational attributes
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="adminprofile",
    )
    admin_type = models.CharField(
        max_length=50,
        choices=AdminType.choices,
        default=AdminType.OTHER,
        help_text=_("Type of administrative role this user holds."),
    )
    position = models.CharField(
        _("Position"),
        max_length=100,
        blank=True,
        null=True,
    )
    school_name = models.CharField(
        _("School Name"),
        max_length=255,
        blank=True,
        null=True,
    )

    def __str__(self):
        return f"Admin ({self.admin_type}): {self.user.name or self.user.email}"


class TeacherProfile(BaseProfile):
    """
    Extended teacher profile containing professional
    and departmental information.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacherprofile",
    )

    classrooms = models.ManyToManyField(
        "academics.ClassRoom",
        related_name="teachers",
        blank=True,
        help_text=_("Classrooms assigned to this teacher."),
    )

    subjects = models.ManyToManyField(
        "academics.Subject",
        related_name="teachers",
        blank=True,
        help_text=_("Subjects this teacher can teach."),
    )

    staff_id = models.CharField(_("Staff ID"), max_length=50, unique=True)
    qualification = models.CharField(max_length=100, blank=True, null=True)
    specialization = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Teacher: {self.user.name or self.user.email}"


class StudentProfile(BaseProfile):
    """
    Stores core academic and identity information for a student.

    This model represents the student's current academic state and
    maintains backward-compatible fields for guardian and address
    information.

    Notes:
        - Legacy fields (guardian_name, guardian_phone, address) are
          retained to avoid breaking existing migrations.
        - More structured contact data is now handled via StudentContact.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="studentprofile",
    )

    classroom = auto_prefetch.ForeignKey(
        "academics.ClassRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )

    student_id = models.CharField(
        _("Student ID"),
        max_length=50,
        unique=True,
        blank=True,
        editable=False,
        help_text=_("Automatically generated unique student identifier."),
    )

    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        blank=True,
    )

    current_class = models.CharField(
        max_length=20,
        choices=AcademicClass.choices,
        blank=True,
        null=True,
        help_text=_("Student's current academic level (e.g. JSS1, SS2)."),
    )

    admission_date = models.DateField(
        blank=True,
        null=True,
        help_text=_("Date student was officially admitted."),
    )

    guardian_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )
    guardian_phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    def save(self, *args, **kwargs):
        """
        Auto-generates a unique student ID on first save.

        Format: STD-XXXXXXXX
        Example: STD-A1B2C3D4
        """
        if not self.student_id:
            self.student_id = f"STD-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Student: {self.user.name or self.user.email}"


class StudentContact(TimeStampedModel):
    """
    Stores guardian and emergency contact information for a student.

    A student can have multiple contacts such as:
        - Father
        - Mother
        - Guardian
        - Emergency contact

    One contact can be marked as the primary contact.
    """

    student = models.ForeignKey(
        "users.StudentProfile",
        on_delete=models.CASCADE,
        related_name="contacts",
    )

    name = models.CharField(
        max_length=255,
        help_text=_("Full name of the contact person."),
    )

    relationship = models.CharField(
        max_length=100,
        help_text=_("Relationship to student e.g. Father, Mother, Guardian."),
    )

    phone = models.CharField(
        max_length=20,
        help_text=_("Primary phone number."),
    )

    email = models.EmailField(
        blank=True,
        null=True,
        help_text=_("Optional email address."),
    )

    is_primary = models.BooleanField(
        default=False,
        help_text=_("Marks this contact as the primary guardian."),
    )

    def __str__(self):
        return f"{self.name} ({self.relationship}) - {self.student}"


class StudentEnrollment(TimeStampedModel):
    """
    Tracks the academic history of a student across sessions and terms.

    This model allows:
        - Promotion tracking
        - Term-based enrollment
        - School transfer history

    Only one active enrollment should exist per student per session.
    """

    student = models.ForeignKey(
        "users.StudentProfile",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )

    classroom = auto_prefetch.ForeignKey(
        "academics.ClassRoom",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )

    session = auto_prefetch.ForeignKey(
        "academics.AcademicSession",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )

    term = auto_prefetch.ForeignKey(
        "academics.AcademicTerm",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_("Indicates the student's current active enrollment."),
    )

    class Meta(auto_prefetch.Model.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["student", "session", "term"],
                name="unique_student_enrollment_per_term",
            ),
        ]

    def __str__(self):
        return f"{self.student} - {self.classroom} ({self.session} - {self.term})"


class ParentProfile(BaseProfile):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parentprofile",
    )
    occupation = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return f"Parent: {self.user.name or self.user.email}"
