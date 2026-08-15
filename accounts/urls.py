from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/edit/", views.edit_profile_view, name="edit_profile"),
    path("settings/", views.settings_view, name="settings"),

    # Wallet login/register (MetaMask / WalletConnect / demo wallet)
    path("wallet-auth/", views.wallet_auth_view, name="wallet_auth"),

    # Google OAuth
    path("google/login/", views.google_login_view, name="google_login"),
    path("google/callback/", views.google_callback_view, name="google_callback"),

    # Email verification
    path("verify-email/", views.verify_email_pending_view, name="verify_email_pending"),
    path("verify-email/resend/", views.resend_verification_view, name="resend_verification"),
    path("verify-email/<uuid:token>/", views.verify_email_confirm_view, name="verify_email_confirm"),

    # Forgot / reset password (Django's built-in views, dark-themed templates)
    path(
        "forgot-password/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/forgot_password.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_sent"),
        ),
        name="forgot_password",
    ),
    path(
        "forgot-password/sent/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_sent.html"),
        name="password_reset_sent",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
]
