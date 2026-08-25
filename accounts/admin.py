"""
accounts/admin.py

Django admin registration for User and Profile models.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, Profile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        "email", "first_name", "last_name", "role",
        "is_email_verified", "terms_accepted_at", "is_active", "created_at",
    ]
    list_filter = ["role", "is_email_verified", "terms_accepted_at", "is_active", "is_staff"]
    search_fields = ["email", "first_name", "last_name", "username"]
    ordering = ["-created_at"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "email_verification_token",
        "terms_accepted_at",
        "terms_accepted_version",
    ]

    fieldsets = BaseUserAdmin.fieldsets + (
        ("DarkForge Art", {
            "fields": (
                "role",
                "phone",
                "avatar_url",
                "is_email_verified",
                "email_verification_token",
                "terms_accepted_at",
                "terms_accepted_version",
            ),
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("DarkForge Art", {
            "fields": ("email", "role", "first_name", "last_name"),
        }),
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "country", "city", "newsletter_opt_in", "created_at"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    readonly_fields = ["created_at"]
