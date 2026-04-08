import logging
from django.core.mail import send_mail
from django.conf import settings
from django.utils.translation import gettext_lazy as _


logger = logging.getLogger(__name__)

def send_approval_notification(profile, action, reason=None):
    """
    Send profile review outcome notification to the user.
    """
    user = profile.user
    profile_type = profile.__class__.__name__.replace("Profile", "").lower()

    subject, message = _build_notification_content(
        user=user,
        profile_type=profile_type,
        action=action,
        reason=reason,
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception(
            "Failed to send %s notification email to %s",
            action,
            user.email,
        )
        return False

def _build_notification_content(*, user, profile_type, action, reason=None):
    """
    Build subject and message content based on review action.
    """
    identifier = user.name or user.email

    if action == "approve":
        subject = _("Your Account Has Been Approved")
        message = _(
            f"Hello {identifier},\n\n"
            f"Your {profile_type} account has been approved. "
            f"You may now access the system.\n\n"
            f"Login URL: {settings.FRONTEND_URL}/login\n\n"
            f"Thank you."
        )

    elif action == "reject":
        subject = _("Your Account Application Status")
        message = _(
            f"Hello {identifier},\n\n"
            f"Your {profile_type} account application has been reviewed and cannot be approved."
        )
        if reason:
            message += _("\n\nReason:\n{reason}").format(reason=reason)

    elif action == "request_changes":
        subject = _("Action Required: Profile Update Needed")
        message = _(
            f"Hello {identifier},\n\n"
            f"Your {profile_type} profile has been reviewed. "
            f"Some required information is missing or needs correction.\n\n"
            f"Please update your profile and resubmit for review."
        )
        if reason:
            message += _("\n\nDetails:\n{reason}").format(reason=reason)

    else:
        raise ValueError("Unsupported notification action.")

    return subject, message
