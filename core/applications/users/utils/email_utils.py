import logging
from django.core.mail import send_mail
from django.conf import settings
from django.utils.translation import gettext_lazy as _


logger = logging.getLogger(__name__)

def send_approval_notification(profile, action, reason=None):
    """
    Send approval/rejection notification to user.
    """
    user = profile.user
    profile_type = profile.__class__.__name__.replace('Profile', '').lower()

    if action == "approve":
        subject = _("Your Account Has Been Approved")
        message = _(
            f"Hello {user.name or user.email},\n\n"
            f"Your {profile_type} account has been approved. "
            f"You can now login to the system.\n\n"
            f"Login URL: {settings.FRONTEND_URL}/login\n\n"
            f"Thank you for joining us!"
        )
    else:
        subject = _("Your Account Application Status")
        message = _(
            f"Hello {user.name or user.email},\n\n"
            f"Your {profile_type} account application has been reviewed and unfortunately "
            f"we cannot approve it at this time."
        )
        if reason:
            message += _("\n\nReason: {reason}").format(reason=reason)

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {user.email}: {str(e)}")
        return False
