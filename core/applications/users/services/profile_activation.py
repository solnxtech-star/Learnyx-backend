import logging

from django.core.exceptions import ValidationError
from django.utils import timezone

from core.applications.users.utils.email_utils import send_approval_notification
from core.helper.enums import AdmissionStatus

logger = logging.getLogger(__name__)




class ProfileActivationService:
    VALID_ACTIONS = {"approve", "reject", "request_changes"}

    @staticmethod
    def activate(*, profile, action, actor, reason=""):
        if action not in ProfileActivationService.VALID_ACTIONS:
            raise ValidationError("Invalid activation action.")

        if profile.status == AdmissionStatus.APPROVED and action == "approve":
            raise ValidationError("Profile is already approved.")

        status_map = {
            "approve": AdmissionStatus.APPROVED,
            "reject": AdmissionStatus.REJECTED,
            "request_changes": AdmissionStatus.REQUIRES_UPDATE,
        }

        profile.status = status_map[action]

        # ✅ Always track reviewer
        profile.reviewed_by = actor
        profile.reviewed_at = timezone.now()

        update_fields = ["status", "reviewed_by", "reviewed_at"]

        # ✅ Only set approval fields when approved
        if action == "approve":
            profile.approved_by = actor
            profile.approved_at = timezone.now()
            update_fields += ["approved_by", "approved_at"]

        # ✅ Save review comment consistently
        if reason:
            profile.review_comment = reason
            update_fields.append("review_comment")

        profile.save(update_fields=update_fields)

        try:
            send_approval_notification(profile, action, reason)
        except Exception:
            logger.exception(
                "Email notification failed for profile %s",
                profile.id,
            )

        return profile
