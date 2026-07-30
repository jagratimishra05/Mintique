from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import LoginAttempt, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-created_at"]
    list_display = [
        "email", "username", "auth_provider", "wallet_address",
        "is_email_verified", "is_verified_creator", "is_staff", "created_at",
    ]
    search_fields = ["email", "username", "wallet_address"]
    list_filter = BaseUserAdmin.list_filter + ("auth_provider", "is_verified_creator")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Mintique Profile", {"fields": ("bio", "avatar", "wallet_address", "wallet_connected_at",
                                          "auth_provider", "is_email_verified", "two_factor_enabled",
                                          "is_verified_creator", "verified_creator_at")}),
    )


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ["identifier", "successful", "ip_address", "attempted_at"]
    list_filter = ["successful"]
