from django.db import models

from core.applications.academics.models import AcademicTerm, AssessmentRecord
from core.helper.models import TimeStampedModel
import auto_prefetch
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

# Create your models here.


class SubjectResult(TimeStampedModel):
    """
    Final subject performance for a student per term.
    """

    student = auto_prefetch.ForeignKey("users.StudentProfile", on_delete=models.CASCADE)
    classroom_subject = auto_prefetch.ForeignKey(
        "academics.Subject", on_delete=models.CASCADE
    )
    term = auto_prefetch.ForeignKey(AcademicTerm, on_delete=models.CASCADE)

    total_ca = models.FloatField(default=0)
    exam_score = models.FloatField(default=0)
    half_term_score = models.FloatField(
        default=0, help_text=_("Score for half-term exams")
    )
    total_score = models.FloatField(default=0)
    average_score = models.FloatField(
        default=0, help_text=_("Average score for the subject")
    )

    grade = models.CharField(
        max_length=3, null=True, blank=True
    )  # Increased to 3 for A'
    grade_point = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True
    )
    comment = models.CharField(max_length=255, null=True, blank=True)

    class Meta(auto_prefetch.Model.Meta):
        unique_together = ("student", "classroom_subject", "term")
        verbose_name = _("Subject Result")
        verbose_name_plural = _("Subject Results")

    def calculate_total_score(self):
        """Calculate total score based on assessment records and policy"""
        from django.db.models import Sum, Avg

        # Get all assessment records for this student, subject, and term
        records = AssessmentRecord.objects.filter(
            student=self.student,
            classroom_subject=self.classroom_subject,
            assessment_type__policy__term=self.term,
        ).select_related("assessment_type")

        total_score = 0

        for record in records:
            if record.score is not None:
                # Calculate weighted score
                percentage = (record.score / record.assessment_type.max_score) * 100
                weighted_score = (percentage * record.assessment_type.weight) / 100
                total_score += weighted_score

        return min(total_score, 100)  # Cap at 100%

    def save(self, *args, **kwargs):
        # Auto-calculate total score if not set
        if not self.total_score:
            self.total_score = self.calculate_total_score()

        # Calculate average (for half-term reports)
        ca_count = AssessmentRecord.objects.filter(
            student=self.student,
            classroom_subject=self.classroom_subject,
            assessment_type__policy__term=self.term,
            assessment_type__category="CA",
        ).count()

        if ca_count > 0:
            self.average_score = self.total_ca / ca_count if self.total_ca else 0

        super().save(*args, **kwargs)


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


class TermReportSummary(TimeStampedModel):
    """
    Aggregates performance across all subjects in a term.
    """

    student = auto_prefetch.ForeignKey("users.StudentProfile", on_delete=models.CASCADE)
    term = auto_prefetch.ForeignKey(AcademicTerm, on_delete=models.CASCADE)
    class_group = auto_prefetch.ForeignKey(
        "academics.ClassRoom", on_delete=models.CASCADE, null=True, blank=True
    )

    total_score = models.FloatField(default=0)
    average_score = models.FloatField(default=0)
    total_points = models.FloatField(default=0)
    gpa = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    target_gpa = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True
    )
    class_position = models.PositiveIntegerField(null=True, blank=True)
    attendance_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    conduct_rating = models.CharField(max_length=20, null=True, blank=True)
    principal_comment = models.TextField(null=True, blank=True)
    form_teacher_comment = models.TextField(null=True, blank=True)

    class Meta(auto_prefetch.Model.Meta):
        unique_together = ("student", "term")
        verbose_name = _("Term Report Summary")
        verbose_name_plural = _("Term Report Summaries")

    def calculate_gpa(self):
        """Calculate GPA based on all subject results"""
        subject_results = SubjectResult.objects.filter(
            student=self.student, term=self.term
        )
        total_points = sum([sr.grade_point or 0 for sr in subject_results])
        count = subject_results.count()
        return total_points / count if count > 0 else 0

    def save(self, *args, **kwargs):
        # Auto-calculate GPA if not set
        if not self.gpa:
            self.gpa = self.calculate_gpa()

        # Calculate total points
        subject_results = SubjectResult.objects.filter(
            student=self.student, term=self.term
        )
        self.total_points = sum([sr.grade_point or 0 for sr in subject_results])

        super().save(*args, **kwargs)




class GradeScale(TimeStampedModel):
    """
    Defines grade brackets for a school (e.g., A = 75-100).
    """

    school = auto_prefetch.ForeignKey("users.School", on_delete=models.CASCADE)

    # ✅ NEW — safe optional fields (won't break existing data)
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

    # ✅ EXISTING FIELDS — unchanged
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
        unique_together = ("school", "grade", "is_honors")
        verbose_name = _("Grade Scale")
        verbose_name_plural = _("Grade Scales")
