from django.db import models
from django.utils.translation import gettext_lazy as _
from core.helper.models import TimeStampedModel
from core.helper.enums import AcademicClass, DayOfWeek, UserRole
import auto_prefetch


class Subject(TimeStampedModel):
    """
    Represents a subject/course taught in the school.
    """
    name = models.CharField(
        max_length=100,
        verbose_name=_("Subject Name"),
        help_text=_("Name of the subject (e.g., Mathematics, Physics)")
    )
    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_("Subject Code"),
        help_text=_("Unique code for the subject (e.g., MATH101)")
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Description"),
        help_text=_("Brief description of the subject")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Is Active"),
        help_text=_("Whether this subject is currently being taught")
    )

    class Meta(auto_prefetch.Model.Meta):
        db_table = "subjects"
        verbose_name = _("Subject")
        verbose_name_plural = _("Subjects")
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class TimeSlot(TimeStampedModel):
    """
    Represents a specific time period in the school day.
    """
    name = models.CharField(
        max_length=50,
        verbose_name=_("Period Name"),
        help_text=_("E.g., 'Period 1', 'Break', 'Lunch'")
    )
    start_time = models.TimeField(
        verbose_name=_("Start Time")
    )
    end_time = models.TimeField(
        verbose_name=_("End Time")
    )
    is_break = models.BooleanField(
        default=False,
        verbose_name=_("Is Break Period"),
        help_text=_("Check if this is a break/lunch period")
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Display Order"),
        help_text=_("Order in which periods appear in the day")
    )

    class Meta(auto_prefetch.Model.Meta):
        db_table = "time_slots"
        verbose_name = _("Time Slot")
        verbose_name_plural = _("Time Slots")
        ordering = ["order", "start_time"]

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"


class ClassSchedule(TimeStampedModel):
    """
    Represents a single class session in the timetable.
    """
    academic_class = models.CharField(
        max_length=50,
        choices=AcademicClass.choices,
        verbose_name=_("Class"),
        help_text=_("Which class this schedule is for")
    )
    day_of_week = models.CharField(
        max_length=20,
        choices=DayOfWeek.choices,
        verbose_name=_("Day of Week")
    )
    time_slot = auto_prefetch.ForeignKey(
        TimeSlot,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name=_("Time Slot")
    )
    subject = auto_prefetch.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name=_("Subject"),
        null=True,
        blank=True,
        help_text=_("Leave blank for break periods")
    )
    teacher = auto_prefetch.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"role": UserRole.TEACHER},
        related_name="teaching_schedules",
        verbose_name=_("Teacher"),
        help_text=_("Teacher assigned to this class")
    )
    room_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Room Number"),
        help_text=_("Classroom or lab number")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Is Active"),
        help_text=_("Whether this schedule is currently in effect")
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Notes"),
        help_text=_("Additional notes or instructions")
    )

    class Meta(auto_prefetch.Model.Meta):
        db_table = "class_schedules"
        verbose_name = _("Class Schedule")
        verbose_name_plural = _("Class Schedules")
        ordering = ["academic_class", "day_of_week", "time_slot__order"]
        unique_together = [
            ["academic_class", "day_of_week", "time_slot"],
        ]

    def __str__(self):
        subject_name = self.subject.name if self.subject else "Break"
        return f"{self.academic_class} - {self.day_of_week} - {self.time_slot.name}: {subject_name}"

    def clean(self):
        from django.core.exceptions import ValidationError
        
        # Validate teacher role
        if self.teacher and self.teacher.role != UserRole.TEACHER:
            raise ValidationError(_("Only users with 'Teacher' role can be assigned to schedules."))
        
        # If it's a break period, subject and teacher should be null
        if self.time_slot and self.time_slot.is_break:
            if self.subject is not None or self.teacher is not None:
                raise ValidationError(_("Break periods cannot have subjects or teachers assigned."))
        
        # If it's not a break, subject is required
        if self.time_slot and not self.time_slot.is_break and not self.subject:
            raise ValidationError(_("Non-break periods must have a subject assigned."))


class Timetable(TimeStampedModel):
    """
    Represents a complete timetable for a specific academic period.
    """
    name = models.CharField(
        max_length=100,
        verbose_name=_("Timetable Name"),
        help_text=_("E.g., 'Fall 2024 Timetable'")
    )
    academic_year = models.CharField(
        max_length=20,
        verbose_name=_("Academic Year"),
        help_text=_("E.g., '2024-2025'")
    )
    term = models.CharField(
        max_length=50,
        verbose_name=_("Term/Semester"),
        help_text=_("E.g., 'Fall Semester', 'First Term'")
    )
    start_date = models.DateField(
        verbose_name=_("Start Date")
    )
    end_date = models.DateField(
        verbose_name=_("End Date")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Is Active"),
        help_text=_("Only one timetable should be active at a time")
    )
    schedules = models.ManyToManyField(
        ClassSchedule,
        related_name="timetables",
        verbose_name=_("Class Schedules"),
        help_text=_("All schedules included in this timetable")
    )

    class Meta(auto_prefetch.Model.Meta):
        db_table = "timetables"
        verbose_name = _("Timetable")
        verbose_name_plural = _("Timetables")
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} ({self.academic_year})"

    def save(self, *args, **kwargs):
        # Ensure only one active timetable
        if self.is_active:
            Timetable.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)