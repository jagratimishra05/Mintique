import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"


def send_transactional_email(subject, message, recipient_list, context=""):
    """Send an email and report *what actually happened*, instead of the
    previous pattern of "no exception raised => tell the user it was sent".

    That pattern is exactly what caused the "Email sent successfully" but
    nothing ever arrives bug: Django's console backend (the automatic
    fallback used whenever EMAIL_HOST_USER / EMAIL_HOST_PASSWORD aren't
    configured — see settings.py) never raises either; it just prints the
    email to the server log instead of handing it to a real mail server.
    From send_mail()'s point of view that's a "successful" send, so the
    calling code had no way to tell the difference from a real delivery.

    Returns one of:
      "sent"    - handed off to a real SMTP/API backend without error
      "console" - EMAIL_HOST_USER / EMAIL_HOST_PASSWORD aren't set, so this
                  only printed to the console/log — NOT a real inbox
      "failed"  - the backend raised (bad credentials, host unreachable,
                  auth rejected, etc.) — see logs/mintique.log for the
                  underlying exception
    """
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=False,
        )
    except Exception:
        logger.exception("Email send failed (%s) — recipients=%s", context, recipient_list)
        return "failed"

    if settings.EMAIL_BACKEND == CONSOLE_BACKEND:
        logger.warning(
            "Email '%s' (%s) to %s was NOT delivered to a real inbox — "
            "EMAIL_BACKEND is still the console backend because "
            "EMAIL_HOST_USER / EMAIL_HOST_PASSWORD aren't set in the "
            "environment. Set them (see .env.example) to actually send mail.",
            subject, context, recipient_list,
        )
        return "console"

    logger.info("Email '%s' (%s) sent to %s via %s", subject, context, recipient_list, settings.EMAIL_BACKEND)
    return "sent"
