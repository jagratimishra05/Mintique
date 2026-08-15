from django.conf import settings


def auth_config(request):
    """Expose which social/wallet login methods are actively configured so
    templates can show honest state (e.g. a 'not configured yet' notice)
    instead of a button that silently fails."""
    return {
        "google_auth_enabled": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        "walletconnect_project_id": settings.WALLETCONNECT_PROJECT_ID,
    }
