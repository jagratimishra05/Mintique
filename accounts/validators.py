import re
import socket

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


# Domains belonging to well-known temporary/disposable email providers.
# Not exhaustive (new ones appear constantly), but it catches the large
# majority of throwaway-inbox services people use to dodge signup flows.
DISPOSABLE_EMAIL_DOMAINS = frozenset({
    "mailinator.com", "mailinator.net", "mailinator.org", "guerrillamail.com",
    "guerrillamail.net", "guerrillamail.org", "guerrillamail.biz", "sharklasers.com",
    "grr.la", "10minutemail.com", "10minutemail.net", "10minemail.com",
    "20minutemail.com", "temp-mail.org", "tempmail.com", "tempmail.net",
    "tempmailo.com", "temp-mail.io", "throwawaymail.com", "trashmail.com",
    "trashmail.net", "trashmail.me", "getnada.com", "nada.email",
    "dispostable.com", "fakeinbox.com", "yopmail.com", "yopmail.net",
    "yopmail.fr", "maildrop.cc", "mailnesia.com", "mintemail.com",
    "mohmal.com", "moakt.com", "moakt.cc", "discard.email", "discardmail.com",
    "emailondeck.com", "spamgourmet.com", "mytemp.email", "tempinbox.com",
    "tempr.email", "throwam.com", "mail-temporaire.fr", "einrot.com",
    "fakemailgenerator.com", "burnermail.io", "mailcatch.com", "spam4.me",
    "getairmail.com", "harakirimail.com", "jetable.org", "1secmail.com",
    "1secmail.net", "1secmail.org", "luxusmail.org", "mailsac.com",
    "inboxbear.com", "tempmailaddress.com", "e4ward.com", "anonaddy.com",
    "mailpoof.com", "tmpmail.org", "tmpmail.net", "tmail.ws", "moakt.ws",
})

# Domains that are structurally valid but obviously not a real inbox — the
# kind of thing someone types to get past a form rather than provide an
# email they can actually be reached at.
PLACEHOLDER_EMAIL_DOMAINS = frozenset({
    "example.com", "example.net", "example.org", "example.edu",
    "test.com", "test.org", "test.net", "testing.com",
    "domain.com", "yourdomain.com", "email.com", "mydomain.com",
    "company.com", "sample.com", "fake.com", "fakemail.com",
    "notreal.com", "nomail.com", "asdf.com", "none.com", "invalid.com",
})

_EMAIL_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def _domain_resolves(domain):
    """Best-effort check that the domain actually exists and can plausibly
    receive mail (has an MX record, or at least resolves at all as a
    fallback for domains that accept mail on their bare A record).

    Network/DNS problems fail *open* — a slow or unreachable resolver
    should never block someone from signing up — so this only rejects a
    domain when it can positively confirm the domain doesn't exist.
    """
    try:
        import dns.resolver

        try:
            dns.resolver.resolve(domain, "MX", lifetime=4)
            return True
        except dns.resolver.NXDOMAIN:
            return False
        except dns.resolver.NoAnswer:
            try:
                dns.resolver.resolve(domain, "A", lifetime=4)
                return True
            except dns.resolver.NXDOMAIN:
                return False
            except Exception:
                return True
        except Exception:
            return True
    except ImportError:
        # dnspython isn't installed — fall back to plain socket resolution,
        # which still catches "this domain doesn't exist at all" typos.
        try:
            socket.getaddrinfo(domain, None)
            return True
        except socket.gaierror:
            return False
        except Exception:
            return True


def validate_deliverable_email(email):
    """Reject temporary/disposable, obviously-fake, or non-existent email
    domains. Raises django.core.exceptions.ValidationError if the address
    doesn't look like something real mail could actually reach.

    This is deliberately layered *on top of* Django's own EmailField syntax
    check, not a replacement for it — callers should still use EmailField
    (or run this after basic format validation).
    """
    email = (email or "").strip()
    if "@" not in email:
        raise ValidationError(_("Enter a valid email address."), code="invalid")

    local_part, sep, domain = email.rpartition("@")
    domain = domain.lower().strip(".")

    if not domain or not _EMAIL_DOMAIN_RE.match(domain):
        raise ValidationError(_("Enter a valid email address."), code="invalid")

    if domain in DISPOSABLE_EMAIL_DOMAINS:
        raise ValidationError(
            _("Temporary or disposable email addresses aren't accepted. Please use a permanent email address."),
            code="disposable_email",
        )

    if domain in PLACEHOLDER_EMAIL_DOMAINS:
        raise ValidationError(
            _("That looks like a placeholder address — enter your real email address."),
            code="placeholder_email",
        )

    if not _domain_resolves(domain):
        raise ValidationError(
            _("We couldn't verify that email domain exists. Double-check for typos."),
            code="undeliverable_email",
        )

    return email


class ComplexPasswordValidator:
    """
    Enforces a strong password policy:
      - at least `min_length` characters (default 8)
      - at least one uppercase letter
      - at least one digit
      - at least one special character

    Plugs into Django's AUTH_PASSWORD_VALIDATORS, so it runs anywhere
    `password_validation.validate_password()` is called (registration,
    password reset, admin "set password", etc.) with no extra work needed
    at the call site.
    """

    SPECIAL_CHARS = r"""!"#$%&'()*+,\-./:;<=>?@[\]^_`{|}~"""

    def __init__(self, min_length=8):
        self.min_length = min_length

    def validate(self, password, user=None):
        problems = []

        if len(password) < self.min_length:
            problems.append(_("at least %d characters") % self.min_length)
        if not re.search(r"[A-Z]", password):
            problems.append(_("one uppercase letter"))
        if not re.search(r"[0-9]", password):
            problems.append(_("one number"))
        if not re.search(f"[{self.SPECIAL_CHARS}]", password):
            problems.append(_("one special character (e.g. ! @ # $ % &)"))

        if problems:
            raise ValidationError(
                _("Password must contain %s.") % ", ".join(problems),
                code="password_too_weak",
            )

    def get_help_text(self):
        return _(
            "Your password must be at least %d characters and include an "
            "uppercase letter, a number, and a special character."
        ) % self.min_length
