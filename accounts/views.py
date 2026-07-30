import logging
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_POST

from mintique.email_utils import send_transactional_email
from walletapp.models import Wallet
from .forms import EmailLoginForm, ProfileForm, RegisterForm, WalletAuthForm
from .models import LoginAttempt, User

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def register_view(request):
    if request.user.is_authenticated:
        return redirect("nftapp:dashboard")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Give every new user an in-app wallet ledger + starter MNQ so
            # they can try the swap feature immediately.
            Wallet.objects.create(user=user, mnq_balance=settings.NEW_USER_MNQ_BONUS)

            verify_url = request.build_absolute_uri(
                reverse("accounts:verify_email_confirm", args=[user.email_verification_token])
            )
            status = send_transactional_email(
                subject="Welcome to Mintique 🎉",
                message=(
                    f"Hi {user.first_name or user.username},\n\n"
                    f"Your Mintique account has been created. Verify your "
                    f"email using this link: {verify_url}\n\n"
                    f"Happy minting!"
                ),
                recipient_list=[user.email],
                context="registration verification email",
            )

            login(request, user)
            if status == "sent":
                messages.success(request, "Account created! Check your email to verify your account.")
            elif status == "console":
                # No exception was raised, but nothing actually left the
                # server — EMAIL_HOST_USER / EMAIL_HOST_PASSWORD aren't
                # configured, so be honest about it instead of claiming the
                # email is on its way to an inbox that will never see it.
                messages.warning(
                    request,
                    "Account created! Email delivery isn't configured on this server yet "
                    "(EMAIL_HOST_USER / EMAIL_HOST_PASSWORD — see .env.example), so the "
                    "verification email wasn't actually delivered. You can request it again "
                    "from your profile once email is set up.",
                )
            else:
                messages.warning(
                    request,
                    "Account created, but the verification email couldn't be sent. "
                    "You can request it again from your profile once email is configured.",
                )
            return redirect("nftapp:dashboard")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("nftapp:dashboard")

    ip = request.META.get("REMOTE_ADDR")
    if request.method == "POST":
        form = EmailLoginForm(request, data=request.POST)
        email = request.POST.get("username", "").lower().strip()

        if form.is_valid():
            user = form.get_user()
            login(request, user)
            LoginAttempt.objects.create(identifier=email, successful=True, ip_address=ip)
            messages.success(request, f"Welcome back, {user.first_name or user.username}!")
            next_url = request.GET.get("next") or "nftapp:dashboard"
            return redirect(next_url)
        else:
            LoginAttempt.objects.create(identifier=email, successful=False, ip_address=ip)
            messages.error(request, "Invalid email or password.")
    else:
        form = EmailLoginForm()
    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "You've been signed out.")
    return redirect("home")


@login_required
def profile_view(request):
    from nftapp.models import NFT, Collection
    from walletapp.models import Transaction

    user = request.user
    stats = {
        "minted": NFT.objects.filter(creator=user).count(),
        "owned": NFT.objects.filter(owner=user, is_burned=False).count(),
        "collections": Collection.objects.filter(owner=user).count(),
        "sold": Transaction.objects.filter(user=user, tx_type=Transaction.TxType.SELL).count(),
    }
    return render(request, "accounts/profile.html", {"stats": stats})


@login_required
def edit_profile_view(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/edit_profile.html", {"form": form})


@login_required
def settings_view(request):
    return render(request, "accounts/settings.html")


# ---------------------------------------------------------------------------
# WALLET LOGIN / REGISTER — sign in with MetaMask, WalletConnect, or the
# built-in demo wallet. First connection auto-creates an account.
# ---------------------------------------------------------------------------
@require_POST
def wallet_auth_view(request):
    form = WalletAuthForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a valid wallet address to continue.")
        return redirect("accounts:login")

    address = form.cleaned_data["wallet_address"]
    user = User.objects.filter(wallet_address__iexact=address).first()

    if user is None:
        username = "wallet_" + get_random_string(8).lower()
        user = User(
            username=username,
            email=f"{username}@wallet.mintique.local",
            wallet_address=address,
            wallet_connected_at=timezone.now(),
            auth_provider=User.AuthProvider.WALLET,
            is_email_verified=True,  # no real inbox to verify for a wallet-only account
        )
        user.set_unusable_password()
        user.save()
        Wallet.objects.create(user=user, mnq_balance=settings.NEW_USER_MNQ_BONUS)
        messages.success(request, f"Wallet connected — account created for {address[:6]}…{address[-4:]}")
    else:
        messages.success(request, f"Welcome back, {address[:6]}…{address[-4:]}")

    login(request, user)
    return redirect("nftapp:dashboard")


# ---------------------------------------------------------------------------
# GOOGLE OAUTH — standard authorization-code flow. Gracefully degrades to a
# clear message if GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET aren't set.
# ---------------------------------------------------------------------------
def google_login_view(request):
    if not (settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET):
        messages.warning(
            request,
            "Google sign-in isn't configured yet. Add GOOGLE_CLIENT_ID / "
            "GOOGLE_CLIENT_SECRET to your environment to enable it.",
        )
        return redirect("accounts:login")

    state = get_random_string(32)
    request.session["google_oauth_state"] = state
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": request.build_absolute_uri(reverse("accounts:google_callback")),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


def google_callback_view(request):
    state = request.GET.get("state")
    if not state or state != request.session.pop("google_oauth_state", None):
        messages.error(request, "Google sign-in session expired. Please try again.")
        return redirect("accounts:login")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "Google sign-in was cancelled.")
        return redirect("accounts:login")

    try:
        token_res = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": request.build_absolute_uri(reverse("accounts:google_callback")),
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]

        userinfo_res = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        userinfo_res.raise_for_status()
        info = userinfo_res.json()
    except (requests.RequestException, KeyError, ValueError):
        messages.error(request, "Couldn't complete Google sign-in. Please try again.")
        return redirect("accounts:login")

    email = info.get("email")
    if not email:
        messages.error(request, "That Google account has no email available.")
        return redirect("accounts:login")

    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        username = "g_" + email.split("@")[0][:20] + "_" + get_random_string(4).lower()
        user = User(
            username=username,
            email=email.lower(),
            first_name=info.get("given_name", ""),
            last_name=info.get("family_name", ""),
            auth_provider=User.AuthProvider.GOOGLE,
            is_email_verified=bool(info.get("email_verified")),
        )
        user.set_unusable_password()
        user.save()
        Wallet.objects.create(user=user, mnq_balance=settings.NEW_USER_MNQ_BONUS)

    login(request, user)
    messages.success(request, f"Signed in as {email} via Google.")
    return redirect("nftapp:dashboard")


# ---------------------------------------------------------------------------
# EMAIL VERIFICATION
# ---------------------------------------------------------------------------
@login_required
def verify_email_pending_view(request):
    return render(request, "accounts/verify_email_pending.html")


def verify_email_confirm_view(request, token):
    user = User.objects.filter(email_verification_token=token).first()
    if user is None:
        messages.error(request, "Invalid or expired verification link.")
        return redirect("accounts:login")

    if not user.is_email_verified:
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
        messages.success(request, "Email verified — your account is fully active.")
    else:
        messages.info(request, "Your email was already verified.")

    if request.user.is_authenticated:
        return redirect("nftapp:dashboard")
    return redirect("accounts:login")


@login_required
@require_POST
def resend_verification_view(request):
    user = request.user
    if user.is_email_verified:
        messages.info(request, "Your email is already verified.")
        return redirect("accounts:verify_email_pending")

    verify_url = request.build_absolute_uri(
        reverse("accounts:verify_email_confirm", args=[user.email_verification_token])
    )
    status = send_transactional_email(
        subject="Verify your Mintique email",
        message=f"Hi {user.first_name or user.username},\n\nVerify your email using this link: {verify_url}",
        recipient_list=[user.email],
        context="resend verification email",
    )
    if status == "sent":
        messages.success(request, "Verification email sent — check your inbox.")
    elif status == "console":
        messages.warning(
            request,
            "This server doesn't have email delivery configured yet "
            "(EMAIL_HOST_USER / EMAIL_HOST_PASSWORD — see .env.example), so no email "
            "actually left the server. Ask your admin to finish that setup.",
        )
    else:
        messages.error(
            request,
            "Couldn't send the verification email. Ask your admin to configure "
            "EMAIL_HOST_USER / EMAIL_HOST_PASSWORD (see .env.example).",
        )
    return redirect("accounts:verify_email_pending")
