# academics/admin.py
from django.contrib import admin

from core.applications.academics.models import AcademicSession
from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import AssessmentPolicy
from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import AssessmentType
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import ClassSchedule
from core.applications.academics.models import StudentClassAssignment
from core.applications.academics.models import StudentSubjectEnrollment
from core.applications.academics.models import Subject
from core.applications.academics.models import TeachingAssignment
from core.applications.academics.models import TermPeriod
from core.applications.academics.models import TimeSlot
from core.applications.academics.models import Timetable


class TenantAdminMixin:
    """
    Reusable admin mixin for TenantAwareModel models.
    Ensures users only see and create data within their school.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # Superuser sees everything
        if request.user.is_superuser:
            return qs

        # School-based restriction
        if request.user.school:
            return qs.filter(school=request.user.school)

        return qs.none()

    def save_model(self, request, obj, form, change):
        # Automatically assign school for non-superusers
        if not request.user.is_superuser:
            obj.school = request.user.school
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Restrict school dropdown for non-superusers.
        """
        if db_field.name == "school" and not request.user.is_superuser:
            kwargs["queryset"] = db_field.related_model.objects.filter(
                id=request.user.school_id
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(AcademicSession)
class AcademicSessionAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name", "school", "is_active", "created_at")
    list_filter = ("school", "is_active")
    search_fields = ("name", "school__name")
    ordering = ("-created_at",)

@admin.register(TermPeriod)
class TermPeriodAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name", "term", "is_active", "start_date", "end_date")
    search_fields = ("name", "school__name")
    ordering = ("-start_date",)

@admin.register(AcademicTerm)
class AcademicTermAdmin(admin.ModelAdmin):
    list_display = ("id", "term_number", "session", "is_active", "term_type")
    list_filter = ("is_active", "term_type")
    search_fields = ("session__name",)
    ordering = ("session__name",)


@admin.register(AssessmentPolicy)
class AssessmentPolicyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "school", "term", "ca_weight", "exam_weight", "is_active")
    list_filter = ("school", "term", "is_active")
    search_fields = ("name", "school__name", "term__name")


@admin.register(AssessmentType)
class AssessmentTypeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "policy",
        "category",
        "count",
        "weight",
        "max_score",
        "order",
    )
    list_filter = ("category", "is_optional")
    search_fields = ("name", "policy__name")
    ordering = ("policy", "order")


@admin.register(AssessmentRecord)
class AssessmentRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "student",
        "status",
        "classroom_subject",
        "assessment_type",
        "index",
        "score",
        "date_taken",
    )
    list_filter = ("assessment_type", "date_taken")
    search_fields = (
        "student__user__email",
        "assessment_type__name",
        "classroom_subject__name",
    )


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "school", "is_active")
    list_filter = ("school", "is_active")
    search_fields = ("name", "code")


@admin.register(ClassRoom)
class ClassRoomAdmin(admin.ModelAdmin):
    list_display = ("id", "academic_class", "arm", "track", "school")
    list_filter = ("academic_class", "school")
    search_fields = ("academic_class", "arm")


@admin.register(TeachingAssignment)
class TeachingAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "teacher", "subject", "classroom")
    list_filter = ("classroom", "subject")
    search_fields = (
        "teacher__user__email",
        "teacher__user__name",
        "subject__name",
    )


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "school", "start_time", "end_time", "is_break", "order")
    list_filter = ("school", "is_break")
    ordering = ("order", "start_time")


@admin.register(ClassSchedule)
class ClassScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "academic_class",
        "day_of_week",
        "time_slot",
        "subject",
        "teacher",
        "school",
        "is_active",
    )
    list_filter = ("school", "academic_class", "day_of_week", "is_active")
    search_fields = ("academic_class", "subject__name", "teacher__email")
    ordering = ("academic_class", "day_of_week")


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "school",
        "academic_year",
        "term",
        "is_active",
        "start_date",
        "end_date",
    )
    list_filter = ("school", "academic_year", "term", "is_active")
    search_fields = ("name", "academic_year", "term")
    filter_horizontal = ("schedules",)


@admin.register(StudentSubjectEnrollment)
class StudentSubjectEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "subject", "assigned_by", "session", "term")
    list_filter = ("assigned_by", "subject")
    search_fields = (
        "student__user__email",
        "student__user__name",
        "subject__name",
    )

@admin.register(StudentClassAssignment)
class StudentClassAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "student", "classroom",
        "academic_session", "academic_term", "is_active"
    )
    # list_filter = ("classroom", "academic_session", "academic_term", "is_active")
    # ordering = ("academic_session", "academic_term")
