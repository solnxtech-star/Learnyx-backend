import uuid
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from core.applications.users.models import (
    AdminProfile,
    TeacherProfile,
    StudentProfile,
    ParentProfile,
    User,
)
from core.helper.enums import UserRole, AdmissionStatus


# Mapping user roles to their respective profile models
ROLE_PROFILE_MAP = {
    UserRole.ADMIN: AdminProfile,
    UserRole.TEACHER: TeacherProfile,
    # UserRole.STUDENT: StudentProfile,
    UserRole.PARENT: ParentProfile,
}


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if not created:
        return

    profile_model = ROLE_PROFILE_MAP.get(instance.role)
    if profile_model and not profile_model.objects.filter(user=instance).exists():
        profile_data = {"user": instance}

        # Auto-generate student_id if student
        if profile_model.__name__ == "StudentProfile":
            profile_data["student_id"] = f"STD-{uuid.uuid4().hex[:8].upper()}"

        profile_model.objects.create(**profile_data)


@receiver(post_save, sender=StudentProfile)
def create_parent_after_student_approval(sender, instance, **kwargs):
    """
    Automatically create a ParentProfile once a student's admission is approved.
    """
    if instance.status == AdmissionStatus.APPROVED:
        user = instance.user
        # Ensure ParentProfile is not already created
        if not ParentProfile.objects.filter(user=user).exists():
            ParentProfile.objects.create(
                user=user,
                phone_number=user.phone_number,
                address=instance.address,
            )
