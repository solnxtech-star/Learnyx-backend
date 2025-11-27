from django.db import models
import auto_prefetch
from django.utils.translation import gettext_lazy as _

from core.helper.models import TimeStampedModel
from core.helper.enums import AcademicClass



# Create your models here.
class ClassRoom(TimeStampedModel):

    school = auto_prefetch.ForeignKey(
        "users.School",
        on_delete=models.CASCADE,
        related_name="classrooms"
    )

    academic_class = models.CharField(
        max_length=20,
        choices=AcademicClass.choices,
        help_text=_("Parent academic class (JSS1, SS2 etc.)")
    )

    arm = models.CharField(
        max_length=10,
        help_text=_("Class arm e.g. A, B, C")
    )

    class Meta(auto_prefetch.Model.Meta):
        unique_together = ("school", "academic_class", "arm")
        ordering = ["academic_class", "arm"]

    def __str__(self):
        return f"{self.academic_class} {self.arm}"
