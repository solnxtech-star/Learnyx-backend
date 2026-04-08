import auto_prefetch
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.applications.users.managers import TenantManager
from core.helper.enums import AcademicClass
from core.helper.enums import AcademicTrack
from core.helper.enums import DayOfWeek
from core.helper.enums import UserRole
from core.helper.models import TenantAwareModel
from core.helper.models import TimeStampedModel

# Create your models here.

class AcademicSession(TenantAwareModel):
    """Represents a school academic year, e.g., 2024/2025."""
    name = models.CharField(
        max_length=20, help_text=_("Name of the session e.g. 2024/2025")
    )
    start_date = models.DateField(
        null=True, blank=True, help_text=_("Session start date")
    )
    end_date = models.DateField(null=True, blank=True, help_text=_("Session end date"))
    is_active = models.BooleanField(
        default=False,
        verbose_name=_("Active"),
        help_text=_("Whether this session is currently active for the school"),
    )

    class Meta(auto_prefetch.Model.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"], name="unique_session_per_school",
            ),
        ]
        verbose_name = _("Academic Session")
        verbose_name_plural = _("Academic Sessions")

    def __str__(self):
        return f"{self.name} ({self.school.name})"

    def clean(self):
        """Validate that end_date is after start_date if both are provided.
        """
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": _("End date must be after start date.")})


class AcademicTerm(TenantAwareModel):
    """Represents a term within an academic session."""
    session = auto_prefetch.ForeignKey(
        "academics.AcademicSession", on_delete=models.CASCADE, related_name="terms"
    )
    term_number = models.PositiveSmallIntegerField(
        default=1, help_text=_("Term number within the session"),
    )
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=False)

    TERM_TYPES = [
        ("HALF_TERM", "Half Term"),
        ("END_OF_TERM", "End of Term"),
        ("FULL_TERM", "Full Term"),
    ]
    term_type = models.CharField(max_length=20, choices=TERM_TYPES, default="FULL_TERM")

    class Meta(auto_prefetch.Model.Meta):
        unique_together = ("session", "term_number")
        ordering = ["term_number"]

    def __str__(self):
        return f"{self.get_term_display_name()} - {self.session.name}"

    def get_term_display_name(self):
        return {
            1: "First Term", 2: "Second Term", 3: "Third Term",
        }.get(self.term_number, f"Term {self.term_number}")

    @property
    def name(self):
        return self.get_term_display_name()

class TermPeriod(TenantAwareModel):
    """
    Represents periods within a term such as:
    - Half Term
    - Exams
    - Holiday
    """

    class PeriodType(models.TextChoices):
        HALF_TERM = "HALF_TERM", _("Half Term Break")
        EXAM = "EXAM", _("Exam Period")
        HOLIDAY = "HOLIDAY", _("Holiday")
        OTHER = "OTHER", _("Other")

    term = auto_prefetch.ForeignKey(
        "academics.AcademicTerm",
        on_delete=models.CASCADE,
        related_name="periods"
    )

    name = models.CharField(
        max_length=100,
        help_text=_("Name of the period e.g Mid-Term Break")
    )

    period_type = models.CharField(
        max_length=20,
        choices=PeriodType.choices
    )

    start_date = models.DateField()
    end_date = models.DateField()

    class Meta(auto_prefetch.Model.Meta):
        ordering = ["start_date"]

    def __str__(self):
        return f"{self.name} ({self.term})"
class AssessmentPolicy(TenantAwareModel):
    """Defines configuration for grading continuous assessments per term."""
    term = auto_prefetch.ForeignKey(
        "academics.AcademicTerm", on_delete=models.CASCADE,
        related_name="policies"
    )
    name = models.CharField(max_length=150, default="Default Policy")
    is_active = models.BooleanField(default=True)
    ca_weight = models.PositiveIntegerField(
        default=40, help_text=_("Continuous Assessment weight (%)")
    )
    exam_weight = models.PositiveIntegerField(
        default=60, help_text=_("Examination weight (%)")
    )

    class Meta(auto_prefetch.Model.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["school", "term", "is_active"],
                condition=Q(is_active=True),
                name="unique_active_policy_per_school_term",
            )
        ]
        verbose_name = _("Assessment Policy")
        verbose_name_plural = _("Assessment Policies")

    def clean(self):
        if self.term.session.school != self.school:
            raise ValidationError(_("Term must belong to the same school as the policy."))

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.school.name} - {self.term} ({self.name})"


class AssessmentType(TimeStampedModel):
    """
    A category of assessment that contributes to total grade.
    Example types: Test, Exam, Assignment, Project
    """

    policy = auto_prefetch.ForeignKey(
        "academics.AssessmentPolicy",
        on_delete=models.CASCADE,
        related_name="assessment_types",
    )
    name = models.CharField(max_length=100)
    category = models.CharField(
        max_length=20,
        choices=[
            ("CA", "Continuous Assessment"),
            ("EXAM", "Examination"),
            ("HALF_TERM", "Half Term Exam"),
            ("PROJECT", "Project"),
            ("ASSIGNMENT", "Assignment"),
        ],
        default="CA",
    )
    count = models.PositiveIntegerField(default=1)
    weight = models.DecimalField(max_digits=5, decimal_places=2)
    max_score = models.PositiveIntegerField(default=100)
    is_optional = models.BooleanField(default=False)
    order = models.PositiveIntegerField(
        default=0, help_text=_("Display order in reports")
    )

    class Meta(auto_prefetch.Model.Meta):
        ordering = ["policy", "order", "name"]
        verbose_name = _("Assessment Type")
        verbose_name_plural = _("Assessment Types")

    def __str__(self):
        return f"{self.name} ({self.weight}%)"

    def clean(self):
        # Validate that weight doesn't exceed 100% when combined with other types in same policy
        if self.weight > 100:
            raise ValidationError(_("Weight cannot exceed 100%"))

        if self.policy:
            total_weight = (
                AssessmentType.objects.filter(policy=self.policy)
                .exclude(pk=self.pk)
                .aggregate(total=models.Sum("weight"))["total"]
                or 0
            )

            if total_weight + self.weight > 100:
                raise ValidationError(
                    _(
                        "Total weight for all assessment types in this policy would exceed 100%"
                    ),
                )


class AssessmentRecord(TimeStampedModel):
    """
    Stores the actual recorded score per student per assessment instance.
    """

    student = auto_prefetch.ForeignKey(
        "users.StudentProfile",
        on_delete=models.CASCADE,
        related_name="assessment_records",
    )
    period = models.ForeignKey(
        "academics.TermPeriod",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    classroom_subject = auto_prefetch.ForeignKey(
        "academics.Subject", on_delete=models.CASCADE, related_name="assessment_records"
    )
    assessment_type = auto_prefetch.ForeignKey(
        AssessmentType, on_delete=models.CASCADE, related_name="records"
    )
    index = models.PositiveIntegerField(help_text=_("Test/Exam number e.g. 1 or 2"))
    score = models.FloatField(null=True, blank=True)
    date_taken = models.DateField(null=True, blank=True)

    objects = TenantManager()

    class Meta(auto_prefetch.Model.Meta):
        unique_together = ("student", "classroom_subject", "assessment_type", "index")
        verbose_name = _("Assessment Record")
        verbose_name_plural = _("Assessment Records")

    def clean(self):
        # Student and Subject must belong to same school
        if self.student.school != self.classroom_subject.school:
            raise ValidationError(
                _("Student and Subject must belong to same school."),
            )

        # AssessmentType must belong to same school
        if self.assessment_type.policy.school != self.student.school:
            raise ValidationError(
                _("Assessment type must belong to same school."),
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.assessment_type.name} {self.index}"

    @property
    def percentage_score(self):
        """Calculate percentage score based on max_score"""
        if self.score is None or self.assessment_type.max_score == 0:
            return 0
        return (self.score / self.assessment_type.max_score) * 100


class Subject(TenantAwareModel):
    """
    Represents an academic subject offered by a school
    (e.g., Mathematics, Physics, Literature).

    Subjects are scoped to a school and can be assigned
    to one or more classrooms.
    """

    name = models.CharField(
        max_length=100,
        help_text="Full name of the subject (e.g., Mathematics, English Language).",
    )

    code = models.CharField(
        max_length=20,
        help_text="Short unique subject code within the school (e.g., MTH101, ENG).",
    )

    credit_hour = models.PositiveSmallIntegerField(
        default=1,
        help_text=_(
            "Academic weight of the subject. Used for GPA, CGPA, "
            "and weighted performance calculations."
        ),
    )

    is_mandatory = models.BooleanField(
        default=False,
        help_text=_(
            "Indicates whether this subject is mandatory for students "
            "in the assigned classrooms."
        ),
    )

    description = models.TextField(
        blank=True,
        null=True,
        help_text=(
            "Optional description providing additional details about the subject, "
            "such as scope, syllabus focus, or special notes."
        ),
    )

    class_rooms = models.ManyToManyField(
        "academics.ClassRoom",
        related_name="subjects",
        blank=True,
        help_text=(
            "Classrooms where this subject is taught. "
            "A subject may be assigned to multiple classrooms."
        ),
    )

    is_active = models.BooleanField(
        default=True,
        help_text=(
            "Indicates whether the subject is currently active. "
            "Inactive subjects are soft-deleted and hidden from normal listings."
        ),
    )
    objects = TenantManager()

    class Meta(auto_prefetch.Model.Meta):
        ordering = ["name"]
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"

        constraints = [
            # Unique subject code per school (active only)
            models.UniqueConstraint(
                fields=["school", "code"],
                condition=Q(is_active=True),
                name="unique_active_subject_code_per_school",
            ),

            # Unique subject name per school (active only)
            models.UniqueConstraint(
                fields=["school", "name"],
                condition=Q(is_active=True),
                name="unique_active_subject_name_per_school",
            ),
        ]

    def __str__(self):
        return f"{self.name}"


class StudentSubjectEnrollment(TimeStampedModel):
    """
    Tracks subjects assigned to each student.

    This allows:
        - Different students in the same class to take different subjects
        - Tracking who assigned the subject and when
        - Future support for grades, electives, and promotions
    """

    student = models.ForeignKey(
        "users.StudentProfile",
        on_delete=models.CASCADE,
        related_name="subject_enrollments",
    )

    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="student_enrollments",
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Admin or staff who assigned this subject",
    )

    session = models.ForeignKey(
        "academics.AcademicSession",
        on_delete=models.CASCADE,
        related_name="student_subject_enrollments",
        help_text="Session in which this subject is assigned",
    )

    term = models.ForeignKey(
        "academics.AcademicTerm",
        on_delete=models.CASCADE,
        related_name="student_subject_enrollments",
        help_text="Term in which this subject is assigned",
    )
    objects = TenantManager()

    class Meta(auto_prefetch.Model.Meta):
        unique_together = ("student", "subject", "session", "term")
        ordering = ["student", "subject"]

    def clean(self):
        if self.student.school != self.subject.school:
            raise ValidationError(_("Student and Subject must belong to same school."))

        if self.session.school != self.student.school:
            raise ValidationError(_("Session must belong to same school."))

        if self.term.session.school != self.student.school:
            raise ValidationError(_("Term must belong to same school."))

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} → {self.subject} ({self.session} - {self.term})"


class ClassRoom(TenantAwareModel):
    school = auto_prefetch.ForeignKey(
        "users.School",
        on_delete=models.CASCADE,
        related_name="classrooms",
    )
    form_teacher = auto_prefetch.ForeignKey(
        "users.TeacherProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="form_classes",
        help_text="Teacher assigned as the form teacher for this class",
    )

    academic_class = models.CharField(
        max_length=20,
        choices=AcademicClass.choices,
        help_text=_("Parent academic class (JSS1, SS2 etc.)"),
    )

    arm = models.CharField(
        max_length=10,
        help_text=_("Class arm e.g. A, B, C"),
    )
    track = models.CharField(
        max_length=20,
        choices=AcademicTrack.choices, default=AcademicTrack.SCIENCE,
        help_text="Academic track (Science, Arts, or Commercial)",
    )
    objects = TenantManager()
    class Meta(auto_prefetch.Model.Meta):
        unique_together = ("school", "academic_class", "arm")
        ordering = ["academic_class", "arm"]

    def __str__(self):
        return f"{self.academic_class} {self.arm}"

class StudentClassAssignment(TimeStampedModel):
    student = auto_prefetch.ForeignKey(
        "users.StudentProfile", on_delete=models.CASCADE,
        related_name="class_assignments",
    )
    classroom = auto_prefetch.ForeignKey(
        "academics.ClassRoom", on_delete=models.CASCADE,
        related_name="student_assignments",
    )
    academic_session = auto_prefetch.ForeignKey(
        "academics.AcademicSession", on_delete=models.CASCADE,
    )
    academic_term = auto_prefetch.ForeignKey(
        "academics.AcademicTerm", null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    is_active = models.BooleanField(default=True)  # indicates current active class
    objects = TenantManager()
    class Meta(auto_prefetch.Model.Meta):
        unique_together = ("student", "classroom", "academic_session")

    def clean(self):
        if self.student.school != self.classroom.school:
            raise ValidationError(
                _("Student and Classroom must belong to same school.")
            )

        if self.academic_session.school != self.classroom.school:
            raise ValidationError(
                _("Session must belong to same school as classroom.")
            )

        if self.academic_term and \
           self.academic_term.session.school != self.classroom.school:
            raise ValidationError(
                _("Term must belong to same school.")
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class TeachingAssignment(TimeStampedModel):
    """
    Defines what a teacher teaches:
    - Which class(es)
    - Which subject(s)
    Fully multi-tenant and scalable.
    """

    teacher = auto_prefetch.ForeignKey(
        "users.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="teaching_assignments",
    )

    classroom = auto_prefetch.ForeignKey(
        "academics.ClassRoom",
        on_delete=models.CASCADE,
        related_name="teaching_assignments",
    )

    subject = auto_prefetch.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="teaching_assignments",
    )
    objects = TenantManager()
    class Meta(auto_prefetch.Model.Meta):
        db_table = "teaching_assignments"
        verbose_name = "Teaching Assignment"
        verbose_name_plural = "Teaching Assignments"
        unique_together = ("teacher", "classroom", "subject")

    def clean(self):
        """
        SaaS MULTI-TENANT VALIDATION:
        Ensure teacher, classroom, and subject belong to the same school.
        """
        if (
            self.teacher.school != self.classroom.school
            or self.teacher.school != self.subject.school
        ):
            raise ValidationError(
                "Teacher, Classroom, and Subject must belong to the same school."
            )


    def save(self, *args, **kwargs):
        # Runs clean() **every time**, including bulk or manual create
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.teacher.user.name} teaches {self.subject.name} in {self.classroom}"




class TimeSlot(TimeStampedModel):
    """
    Represents a specific period in a school day.
    Multi-tenant: each school has unique TimeSlots.
    """

    school = models.ForeignKey(
        "users.School",
        on_delete=models.CASCADE,
        related_name="time_slots",
    )

    name = models.CharField(max_length=50)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_break = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    objects = TenantManager()

    class Meta(auto_prefetch.Model.Meta):
        db_table = "time_slots"
        verbose_name = _("Time Slot")
        verbose_name_plural = _("Time Slots")
        ordering = ["order", "start_time"]
        unique_together = ("school", "order")

    def __str__(self):
        return f"{self.name} ({self.start_time} - {self.end_time})"

class ClassSchedule(TimeStampedModel):
    """
    Represents a single class session for a school.
    Enforces strict multi-tenant ownership.
    """

    school = models.ForeignKey(
        "users.School",
        on_delete=models.CASCADE,
        related_name="class_schedules",

    )

    academic_class = models.CharField(max_length=50, choices=AcademicClass.choices)
    day_of_week = models.CharField(max_length=20, choices=DayOfWeek.choices)

    time_slot = auto_prefetch.ForeignKey(
        TimeSlot,
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    subject = auto_prefetch.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="schedules",
        null=True,
        blank=True,
    )
    teacher = auto_prefetch.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"role": UserRole.TEACHER},
        related_name="teaching_schedules",
    )
    room_number = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    class Meta(auto_prefetch.Model.Meta):
        db_table = "class_schedules"
        verbose_name = _("Class Schedule")
        verbose_name_plural = _("Class Schedules")
        ordering = ["academic_class", "day_of_week", "time_slot__order"]
        unique_together = [
            ["school", "academic_class", "day_of_week", "time_slot"],
        ]

    def __str__(self):
        subject_name = self.subject.name if self.subject else "Break"
        return f"{self.academic_class} - {self.day_of_week} - {subject_name}"
    # 🔒 MULTI-TENANT VALIDATION
    def clean(self):
        # 1. Teacher must belong to the same school
        if self.teacher and self.teacher.school != self.school:
            raise ValidationError(_("Teacher must belong to the same school."))

        # 2. Foreign keys must match same school
        if self.time_slot.school != self.school:
            raise ValidationError(_("Time slot does not belong to this school."))

        if self.subject and self.subject.school != self.school:
            raise ValidationError(_("Subject does not belong to this school."))

        # 3. Teacher role
        if self.teacher and self.teacher.role != UserRole.TEACHER:
            raise ValidationError(_("Only teachers can be assigned."))

        # 4. Break period rules
        if self.time_slot.is_break and (self.subject or self.teacher):
            raise ValidationError(_("Break periods cannot have subjects or teachers."))

        if not self.time_slot.is_break and not self.subject:
            raise ValidationError(_("Non-break periods must have a subject."))

class Timetable(TimeStampedModel):
    """
    Represents a complete timetable for a specific school.
    """

    school = models.ForeignKey(
        "users.School",
        on_delete=models.CASCADE,
        related_name="timetables",
    )

    name = models.CharField(max_length=100)
    academic_year = models.CharField(max_length=20)
    term = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    schedules = models.ManyToManyField(
        ClassSchedule,
        related_name="timetables",
    )

    class Meta(auto_prefetch.Model.Meta):
        db_table = "timetables"
        verbose_name = _("Timetable")
        verbose_name_plural = _("Timetables")
        ordering = ["-start_date"]
        unique_together = ("school", "name", "academic_year", "term")

    def __str__(self):
        return f"{self.name} ({self.academic_year})"

    #  MULTI-TENANT SAFETY
    def clean(self):
        for schedule in self.schedules.all():
            if schedule.school != self.school:
                raise ValidationError(
                    _("All schedules must belong to the same school.")
                )

    def save(self, *args, **kwargs):
        # Only one active timetable PER SCHOOL
        if self.is_active:
            Timetable.objects.filter(
                school=self.school,
                is_active=True
            ).exclude(pk=self.pk).update(is_active=False)

        super().save(*args, **kwargs)
