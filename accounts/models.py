import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model. Email is the unique login identifier; a wallet can be
    linked later (wallet connection is only required at mint-time, not at
    registration/login).
    """

    class AuthProvider(models.TextChoices):
        EMAIL = "email", "Email"
        GOOGLE = "google", "Google"
        WALLET = "wallet", "Wallet"

    email = models.EmailField(unique=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    bio = models.CharField(max_length=255, blank=True)

    wallet_address = models.CharField(max_length=64, blank=True, null=True, unique=False)
    wallet_connected_at = models.DateTimeField(blank=True, null=True)

    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.UUIDField(default=uuid.uuid4, editable=False)

    two_factor_enabled = models.BooleanField(default=False)

    auth_provider = models.CharField(max_length=20, choices=AuthProvider.choices, default=AuthProvider.EMAIL)

    # Creator verification — powers the "verified creator" badge across
    # profiles, NFT cards, and collection pages. Granted by staff via admin
    # for now; a request/review workflow can hang off this later without
    # a schema change.
    is_verified_creator = models.BooleanField(default=False)
    verified_creator_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email

    @property
    def has_wallet(self):
        return bool(self.wallet_address)

    @property
    def initials(self):
        return (self.first_name[:1] or self.username[:1] or "U").upper()


class LoginAttempt(models.Model):
    """Tracks failed login attempts per identifier (email/IP) for basic
    brute-force throttling — see accounts.middleware.LoginRateLimitMiddleware.
    """
    identifier = models.CharField(max_length=255, db_index=True)
    attempted_at = models.DateTimeField(auto_now_add=True)
    successful = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    class Meta:
        ordering = ["-attempted_at"]
