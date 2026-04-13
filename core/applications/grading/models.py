import auto_prefetch
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Trim
from django.db.models.functions import Upper
from django.utils.translation import gettext_lazy as _

from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import AssessmentRecord
from core.helper.enums import Stage
from core.helper.models import TenantAwareModel
from core.helper.models import TimeStampedModel

# Create your models here.


class SubjectResult(TimeStampedModel):
    """
    Subject performance for a student per term, per assessment stage.
    A student has one HALF_TERM result and one END_OF_TERM result
    for the same subject in the same term — they never overwrite each other.
    """

    class Stage(models.TextChoices):
        HALF_TERM = "HALF_TERM", _("Half Term")
        END_OF_TERM = "END_OF_TERM", _("End of Term")

    student = auto_prefetch.ForeignKey(
        "users.StudentProfile", on_delete=models.CASCADE, related_name="subject_results"
    )
    classroom_subject = auto_prefetch.ForeignKey(
        "academics.Subject", on_delete=models.CASCADE, related_name="subject_results"
    )
    term = auto_prefetch.ForeignKey(
        AcademicTerm, on_delete=models.CASCADE, related_name="subject_results"
    )
    stage = models.CharField(
        max_length=20,
        choices=Stage.choices,
        default=Stage.END_OF_TERM,
        help_text=_("Assessment stage this result belongs to"),
    )

    total_ca = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text=_("Aggregated continuous assessment score")
    )
    exam_score = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text=_("End of term exam score")
    )
    half_term_score = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text=_("Score at half term checkpoint")
    )
    total_score = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text=_("Final weighted total score out of 100")
    )
    average_score = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text=_("Average across assessment categories")
    )

    grade = models.CharField(max_length=3, null=True, blank=True)
    grade_point = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True
    )
    comment = models.CharField(max_length=255, null=True, blank=True)
    is_published = models.BooleanField(default=False)

    class Meta(auto_prefetch.Model.Meta):
        unique_together = ("student", "classroom_subject", "term", "stage")
        verbose_name = _("Subject Result")
        verbose_name_plural = _("Subject Results")
        ordering = ["term", "stage"]

    def __str__(self):
        return f"{self.student} | {self.classroom_subject} | {self.term} | {self.get_stage_display()}"


class TermReportSummary(TimeStampedModel):
    """
    Aggregates performance across all subjects for a student in a term.
    Scoped per stage so half-term and end-of-term summaries coexist.
    Class position is computed within the class group at each stage.
    """

    student = auto_prefetch.ForeignKey(
        "users.StudentProfile", on_delete=models.CASCADE, related_name="term_summaries"
    )
    term = auto_prefetch.ForeignKey(
        AcademicTerm, on_delete=models.CASCADE, related_name="term_summaries"
    )
    class_group = auto_prefetch.ForeignKey(
        "academics.ClassRoom", on_delete=models.CASCADE, related_name="term_summaries",
        null=True,
        blank=True,
    )
    stage = models.CharField(
        max_length=20,
        choices=SubjectResult.Stage.choices,
        default=SubjectResult.Stage.END_OF_TERM,
        help_text=_("Assessment stage this summary belongs to"),
    )

    total_score = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        help_text=_("Sum of total_score across all subjects")
    )
    average_score = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text=_("Average total_score across all subjects")
    )
    total_points = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text=_("Sum of grade_points across all subjects")
    )
    gpa = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text=_("Grade point average for the term")
    )
    target_gpa = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True
    )
    class_position = models.PositiveIntegerField(null=True, blank=True)
    attendance_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    conduct_rating = models.CharField(max_length=20, null=True, blank=True)
    principal_comment = models.TextField(null=True, blank=True)
    form_teacher_comment = models.TextField(null=True, blank=True)

    class Meta(auto_prefetch.Model.Meta):
        unique_together = ("student", "term", "stage", "class_group")
        verbose_name = _("Term Report Summary")
        verbose_name_plural = _("Term Report Summaries")
        ordering = ["term", "stage", "class_position"]

    def __str__(self):
        return f"{self.student} | {self.term} | {self.get_stage_display()} | {self.class_group}"





class TeacherComment(TimeStampedModel):
    """
    Stores teacher comments for student performance in subjects.
    """

    subject_result = auto_prefetch.ForeignKey(
        SubjectResult, on_delete=models.CASCADE, related_name="teacher_comments"
    )
    teacher = auto_prefetch.ForeignKey("users.TeacherProfile", on_delete=models.CASCADE)
    comment = models.TextField()
    comment_type = models.CharField(
        max_length=20,
        choices=[
            ("STRENGTH", "Strength"),
            ("WEAKNESS", "Weakness"),
            ("GENERAL", "General"),
            ("IMPROVEMENT", "Area for Improvement"),
        ],
        default="GENERAL",
    )

    class Meta(auto_prefetch.Model.Meta):
        verbose_name = _("Teacher Comment")
        verbose_name_plural = _("Teacher Comments")
        ordering = ["subject_result", "comment_type"]

    def __str__(self):
        return f"{self.subject_result} - {self.comment_type}"


class TargetGrade(TimeStampedModel):
    """
    Stores target grades for students in subjects.
    """

    student = auto_prefetch.ForeignKey(
        "users.StudentProfile", on_delete=models.CASCADE,
        related_name="target_grades",
    )
    classroom_subject = auto_prefetch.ForeignKey(
        "academics.Subject", on_delete=models.CASCADE
    )
    term = auto_prefetch.ForeignKey(AcademicTerm, on_delete=models.CASCADE)
    target_grade = models.CharField(max_length=3)
    target_point = models.DecimalField(max_digits=3, decimal_places=1)
    current_grade = models.CharField(max_length=3, null=True, blank=True)
    current_point = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True
    )

    class Meta(auto_prefetch.Model.Meta):
        unique_together = ("student", "classroom_subject", "term")
        verbose_name = _("Target Grade")
        verbose_name_plural = _("Target Grades")

    def __str__(self):
        return f"{self.student} - {self.classroom_subject}: {self.current_grade} → {self.target_grade}"



class GradeScale(TenantAwareModel):
    """
    Defines grade brackets for a school (e.g., A = 75-100).
    """

    term = auto_prefetch.ForeignKey(
        "academics.AcademicTerm",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="grade_scales",
    )
    class_room = auto_prefetch.ForeignKey(
        "academics.ClassRoom",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="grade_scales",
    )

    version = models.PositiveIntegerField(default=1)

    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)

    is_published = models.BooleanField(default=False)

    grade = models.CharField(max_length=3)
    display_name = models.CharField(
        max_length=50, null=True, blank=True, help_text=_("e.g., A' for honors")
    )
    min_score = models.PositiveIntegerField()
    max_score = models.PositiveIntegerField()
    point = models.DecimalField(max_digits=3, decimal_places=1)
    remark = models.CharField(max_length=255, null=True, blank=True)
    is_honors = models.BooleanField(
        default=False, help_text=_("Whether this is an honors grade (A')")
    )
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ["-max_score"]
        verbose_name = _("Grade Scale")
        verbose_name_plural = _("Grade Scales")

        constraints = [
            # -------------------------------------------------
            # UNIQUE active grade per scope (school + term + class)
            # -------------------------------------------------
            models.UniqueConstraint(
                Upper(Trim("grade")),
                "school",
                "term",
                "class_room",
                condition=Q(is_active=True),
                name="unique_active_grade_per_scope",
            ),

            # -------------------------------------------------
            # Prevent overlapping score ranges per scope
            # (DB-level protection, serializer already checks)
            # -------------------------------------------------
            models.CheckConstraint(
                condition=Q(min_score__lte=models.F("max_score")),
                name="min_score_lte_max_score",
            ),

            models.CheckConstraint(
                condition=Q(min_score__gte=0) & Q(max_score__lte=100),
                name="score_range_0_100",
            ),

            # -------------------------------------------------
            # Prevent negative or insane points
            # -------------------------------------------------
            models.CheckConstraint(
                condition=Q(point__gte=0) & Q(point__lte=5),
                name="point_between_0_and_5",
            ),
        ]

    @classmethod
    def active_for_school(cls, school):
        """Return only active grade scales for the given school."""
        return cls.objects.for_school(school).filter(is_active=True)
