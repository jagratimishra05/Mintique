from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta


class LoginRateLimitMiddleware:
    """
    Very lightweight brute-force protection: if an identifier (email) has
    5+ failed login attempts within the last 10 minutes, block further
    attempts and show a warning instead of hitting the auth backend again.

    This is intentionally simple (DB-backed, no external cache) so the demo
    runs anywhere. For production, swap in django-axes or django-ratelimit
    backed by Redis.
    """
    WINDOW_MINUTES = 10
    MAX_ATTEMPTS = 5

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and request.path == reverse("accounts:login"):
            from .models import LoginAttempt

            email = request.POST.get("username", "").lower().strip()
            if email:
                window_start = timezone.now() - timedelta(minutes=self.WINDOW_MINUTES)
                recent_failures = LoginAttempt.objects.filter(
                    identifier=email, successful=False, attempted_at__gte=window_start
                ).count()
                if recent_failures >= self.MAX_ATTEMPTS:
                    messages.error(
                        request,
                        "Too many failed login attempts. Please try again in a "
                        f"few minutes or reset your password."
                    )
                    return redirect("accounts:login")

        return self.get_response(request)
