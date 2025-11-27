from django.contrib import admin
from core.applications.academics.models import ClassRoom

# Register your models here.

@admin.register(ClassRoom)
class ClassRoomAdmin(admin.ModelAdmin):
    list_display = ("id", "school", "academic_class", "arm", "created_at", "updated_at")
    list_filter = ("school", "academic_class")
    search_fields = ("academic_class", "arm", "school__name")
