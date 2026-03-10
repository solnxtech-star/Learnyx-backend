import secrets
import uuid
from typing import ClassVar

import auto_prefetch
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from core.applications.academics.models import ClassRoom
from core.applications.academics.models import StudentClassAssignment
from core.helper.enums import AcademicClass
from core.helper.enums import AdminType
from core.helper.enums import AdmissionStatus
from core.helper.enums import Gender
from core.helper.enums import UserRole
from core.helper.models import TenantAwareModel
from core.helper.models import TimeStampedModel

from .managers import SchoolManager
from .managers import TenantManager
from .managers import UserManager


# --------------------------
# Core School Model
# --------------------------
class School(models.Model):
    """Represents a school tenant in the SaaS platform."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, db_index=True)
    school_code = models.CharField(
        max_length=12, unique=True, editable=False, db_index=True,
        help_text=_("Unique auto-generated code used for user onboarding"),
    )
    is_active = models.BooleanField(default=True)
    subscription_plan = models.CharField(max_length=50, blank=True, null=True)
    subscription_expiry = models.DateField(blank=True, null=True)
    max_students = models.PositiveIntegerField(default=1000)
    address = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SchoolManager()
    class Meta:
        ordering = ["name"]
        verbose_name = _("School")
        verbose_name_plural = _("Schools")

    def __str__(self):
        return f"{self.name} ({self.school_code})"

    def save(self, *args, **kwargs):
        """
        Generate slug and school_code if missing.
        Validate subscription expiry date.
        """
        if not self.slug:
            self.slug = slugify(self.name)

        if not self.school_code:
            # Retry generation to avoid collisions
            for _ in range(5):
                code = f"SCH-{secrets.token_hex(4).upper()}"
                if not School.objects.filter(school_code=code).exists():
                    self.school_code = code
                    break
            else:
                raise ValidationError(_("Unable to generate unique school_code."))

        # Optional subscription validation
        if self.subscription_expiry and self.subscription_expiry < self.created_at.date():
            raise ValidationError(_("Subscription expiry cannot be in the past."))

        super().save(*args, **kwargs)


# --------------------------
# Custom User Model
# --------------------------
class User(AbstractUser):
    """Custom user with email login and optional school assignment."""
    school = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    name = models.CharField(_("Full Name"), max_length=255, blank=True)
    email = models.EmailField(_("Email Address"), unique=True)
    phone_number = models.CharField(
        _("Phone Number"), max_length=20, blank=True, null=True
    )
    role = models.CharField(
        _("User Role"), max_length=20,
        choices=UserRole.choices, default=UserRole.STUDENT
    )
    is_verified = models.BooleanField(_("Email Verified"), default=False)
    date_joined = models.DateTimeField(_("Date Joined"), auto_now_add=True)
    last_login = models.DateTimeField(_("Last Login"), blank=True, null=True)

    # Remove default Django fields we don't need
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


# --------------------------
# Base Profile for All Roles
# --------------------------
class BaseProfile(TimeStampedModel):
    """Abstract profile base with tenant awareness and approval workflow."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20, choices=AdmissionStatus.choices,
        default=AdmissionStatus.PENDING
    )
    approved_by = models.CharField(max_length=100, blank=True, null=True)

    @property
    def school(self):
        return self.user.school

    class Meta(auto_prefetch.Model.Meta):
        abstract = True


# --------------------------
# Admin Profile
# --------------------------
class AdminProfile(BaseProfile):
    admin_type = models.CharField(
        max_length=50, choices=AdminType.choices,
        default=AdminType.OTHER
    )
    position = models.CharField(max_length=100, blank=True, null=True)
    school_name = models.CharField(max_length=255, blank=True, null=True)

    objects = TenantManager()

    def __str__(self):
        return f"Admin ({self.admin_type}): {self.user.name or self.user.email}"


# --------------------------
# Teacher Profile
# --------------------------
class TeacherProfile(BaseProfile):
    classrooms = models.ManyToManyField(
        "academics.ClassRoom", related_name="teachers", blank=True
    )
    subjects = models.ManyToManyField(
        "academics.Subject", related_name="teachers", blank=True
    )
    staff_id = models.CharField(max_length=50, unique=True)
    qualification = models.CharField(max_length=100, blank=True, null=True)
    specialization = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)

    objects = TenantManager()

    def __str__(self):
        return f"Teacher: {self.user.name or self.user.email}"


# --------------------------
# Student Profile
# --------------------------
class StudentProfile(BaseProfile):
    classroom = auto_prefetch.ForeignKey(
        "academics.ClassRoom", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="students",
    )
    student_id = models.CharField(max_length=50, unique=True, blank=True, editable=False)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    current_class = models.CharField(
        max_length=20, choices=AcademicClass.choices, \
        blank=True, null=True
    )
    admission_date = models.DateField(blank=True, null=True)
    guardian_name = models.CharField(max_length=100, blank=True, null=True)
    guardian_phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)

    objects = TenantManager()

    def save(self, *args, **kwargs):
        if not self.student_id:
            self.student_id = f"STD-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    @property
    def current_assignment(self) -> StudentClassAssignment:
        return self.class_assignments.filter(is_active=True).select_related(
            "classroom", "academic_session", "academic_term"
        ).first()

    @property
    def active_classroom(self):
        assignment = self.current_assignment
        return assignment.classroom if assignment else None

    @property
    def active_class(self):
        classroom = self.active_classroom
        return classroom.academic_class if classroom else None

    def sync_current_class_fields(self, classroom: ClassRoom = None):
        if classroom:
            self.classroom = classroom
            self.current_class = classroom.academic_class
        else:
            assignment = self.current_assignment
            if assignment:
                self.classroom = assignment.classroom
                self.current_class = assignment.classroom.academic_class
            else:
                self.classroom = None
                self.current_class = None
        super().save(update_fields=["classroom", "current_class"])

    def __str__(self):
        return f"Student: {self.user.name or self.user.email}"


# --------------------------
# Student Contact
# --------------------------
class StudentContact(TenantAwareModel):
    student = models.ForeignKey(
        "users.StudentProfile", on_delete=models.CASCADE,
        related_name="contacts"
    )
    name = models.CharField(max_length=255)
    relationship = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    is_primary = models.BooleanField(default=False)

    objects = TenantManager()

    class Meta(auto_prefetch.Model.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["student", "is_primary"],
                condition=models.Q(is_primary=True),
                name="unique_primary_contact_per_student",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.relationship}) - {self.student}"


# --------------------------
# Student Enrollment
# --------------------------
class StudentEnrollment(TenantAwareModel):
    student = models.ForeignKey(
        "users.StudentProfile", on_delete=models.CASCADE,
        related_name="enrollments"
    )
    classroom = auto_prefetch.ForeignKey(
        "academics.ClassRoom", on_delete=models.CASCADE, related_name="enrollments",
    )
    session = auto_prefetch.ForeignKey(
        "academics.AcademicSession", on_delete=models.CASCADE, related_name="enrollments",
    )
    term = auto_prefetch.ForeignKey(
        "academics.AcademicTerm", on_delete=models.CASCADE, related_name="enrollments",
    )
    is_active = models.BooleanField(default=True)


    class Meta(auto_prefetch.Model.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["student", "classroom", "session", "term"],
                name="unique_student_enrollment",
            ),
        ]

    def __str__(self):
        return f"{self.student} - {self.classroom} ({self.session} - {self.term})"


# --------------------------
# Parent Profile
# --------------------------
class ParentProfile(BaseProfile):
    occupation = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    objects = TenantManager()

    def __str__(self):
        return f"Parent: {self.user.name or self.user.email}"
