import logging

from django.core.exceptions import ValidationError

from core.applications.users.utils.email_utils import send_approval_notification
from core.helper.enums import AdmissionStatus

logger = logging.getLogger(__name__)


class ProfileActivationService:
    @staticmethod
    def activate(*, profile, action, actor, reason=""):
        if action not in {"approve", "reject"}:
            raise ValidationError("Invalid activation action.")

        if profile.status == AdmissionStatus.APPROVED and action == "approve":
            raise ValidationError("Profile is already approved.")

        profile.status = (
            AdmissionStatus.APPROVED
            if action == "approve"
            else AdmissionStatus.REJECTED
        )
        profile.approved_by = actor.email or actor.name or str(actor.id)
        profile.save(update_fields=["status", "approved_by"])

        try:
            send_approval_notification(profile, action, reason)
        except Exception:
            logger.exception(
                "Email notification failed for profile %s",
                profile.id,
            )

        return profile
