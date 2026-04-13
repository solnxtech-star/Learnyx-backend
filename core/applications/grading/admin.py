from django.contrib import admin

from core.applications.grading.models import GradeScale
from core.applications.grading.models import SubjectResult
from core.applications.grading.models import TargetGrade
from core.applications.grading.models import TermReportSummary

# from core.applications.grading.models import TeacherComment


# Register your models here.

@admin.register(SubjectResult)
class SubjectResultAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "classroom_subject",
        "term",
        "total_score",
        "grade",
        "grade_point",
    )
    search_fields = ("student__user__name", "classroom_subject__name", "term__name")
    list_filter = ("term", "classroom_subject")

# @admin.register(TeacherComment)
# class TeacherCommentAdmin(admin.ModelAdmin):
#     list_display = ("teacher", "student", "term", "comment_type", "created_at")
#     search_fields = ("teacher__user__name", "student__user__name", "comment_type")
#     list_filter = ("term", "comment_type")


@admin.register(TargetGrade)
class TargetGradeAdmin(admin.ModelAdmin):
    list_display = (
        "id", "student", "classroom_subject", "term", "target_grade", "target_point",
    )
    search_fields = ("student__user__name", "classroom_subject__name", "term__name")
    list_filter = ("term", "classroom_subject")

@admin.register(GradeScale)
class GradeScaleAdmin(admin.ModelAdmin):
    list_display = (
        "id", "school", "term", "is_active", "min_score", "max_score",
        "class_room", "version", "effective_from",
    )
    search_fields = ("term__name", "class_room__name", "version")
    list_filter = ("term", "class_room")


@admin.register(TermReportSummary)
class TermReportSummaryAdmin(admin.ModelAdmin):
    list_display = (
        "id", "student",
        "term","gpa",
        "class_position", "class_group",
        "average_score",
    )
    search_fields = ("student__user__name", "term__name")
    list_filter = ("term",)
