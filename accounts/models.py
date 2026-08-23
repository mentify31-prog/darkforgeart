"""
accounts/models.py

Custom User model + Profile.
email is the login field.
role drives access control: customer vs admin.
Table prefix: dfa_
"""
import os
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


def table_name(base_name: str) -> str:
    """Return a prefixed table name using DB_TABLE_PREFIX env var."""
    prefix = os.getenv("DB_TABLE_PREFIX", "dfa_")
    return f"{prefix}{base_name}"


class User(AbstractUser):
    """
    Central user model for DarkForge Art.
    role field drives access control: customer or admin.
    Email is the login identifier.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", _("Admin")
        CUSTOMER = "customer", _("Customer")

    # Override email to be required and unique
    email = models.EmailField(_("email address"), unique=True)

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        db_index=True,
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text=_("E.164 format, e.g. +254700000000"),
    )
    avatar_url = models.CharField(
        max_length=1024,
        blank=True,
        help_text=_("Profile photo image URL"),
    )
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text=_("Token sent in verification email"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Use email as the login field
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "first_name", "last_name"]

    class Meta:
        db_table = table_name("users")
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_full_name()} ({self.email}) [{self.role}]"

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    def get_dashboard_url(self):
        """Return the appropriate dashboard URL for this user's role."""
        from django.urls import reverse
        if self.is_admin:
            return reverse("accounts:admin_dashboard")
        return reverse("accounts:dashboard")

    def regenerate_verification_token(self):
        """Issue a fresh email-verification token."""
        self.email_verification_token = uuid.uuid4()
        self.save(update_fields=["email_verification_token"])
        return self.email_verification_token


class Profile(models.Model):
    """
    Extended profile for DarkForge Art customers.
    Kept separate so User stays lean.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    bio = models.TextField(
        blank=True,
        help_text=_("Tell us a bit about yourself (optional)"),
    )
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    newsletter_opt_in = models.BooleanField(
        default=True,
        help_text=_("Receive email updates about new artwork and releases"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = table_name("profiles")

    def __str__(self):
        return f"Profile: {self.user.get_full_name()}"
