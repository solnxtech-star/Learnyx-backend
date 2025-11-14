from django.db import models
from django.utils.translation import gettext_lazy as _


class UserRole(models.TextChoices):
    ADMIN = "admin", _("Admin")
    TEACHER = "teacher", _("Teacher")
    STUDENT = "student", _("Student")
    PARENT = "parent", _("Parent")


class Gender(models.TextChoices):
    MALE = "male", _("Male")
    FEMALE = "female", _("Female")


class AdmissionStatus(models.TextChoices):
    PENDING = "pending", _("Pending Approval")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Rejected")


class AcademicClass(models.TextChoices):
    NURSERY1 = "Nursery 1", _("Nursery 1")
    NURSERY2 = "Nursery 2", _("Nursery 2")
    PREP = "Prep", _("Preparatory")
    PRIMARY1 = "Primary 1", _("Primary 1")
    PRIMARY2 = "Primary 2", _("Primary 2")
    PRIMARY3 = "Primary 3", _("Primary 3")
    PRIMARY4 = "Primary 4", _("Primary 4")
    PRIMARY5 = "Primary 5", _("Primary 5")
    PRIMARY6 = "Primary 6", _("Primary 6")
    JSS1 = "JSS1", _("Junior Secondary 1")
    JSS2 = "JSS2", _("Junior Secondary 2")
    JSS3 = "JSS3", _("Junior Secondary 3")
    SS1 = "SS1", _("Senior Secondary 1")
    SS2 = "SS2", _("Senior Secondary 2")
    SS3 = "SS3", _("Senior Secondary 3")

class DayOfWeek(models.TextChoices):
    """Day of the week choices"""
    MONDAY = "MONDAY", _("Monday")
    TUESDAY = "TUESDAY", _("Tuesday")
    WEDNESDAY = "WEDNESDAY", _("Wednesday")
    THURSDAY = "THURSDAY", _("Thursday")
    FRIDAY = "FRIDAY", _("Friday")
    SATURDAY = "SATURDAY", _("Saturday")
    SUNDAY = "SUNDAY", _("Sunday")