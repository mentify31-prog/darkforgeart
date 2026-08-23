"""
commissions/models.py

Commission request, revision, and messaging system for DarkForge Art.
This is the custom artwork pipeline: request → quote → deposit → work → preview → final delivery.

Table prefix: dfa_
"""
import os

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def table_name(base_name: str) -> str:
    prefix = os.getenv("DB_TABLE_PREFIX", "dfa_")
    return f"{prefix}{base_name}"


class Commission(models.Model):
    """
    A custom artwork commission request from a customer.
    """

    class Tier(models.TextChoices):
        BASIC = "basic", _("Basic — Digital artwork")
        PREMIUM = "premium", _("Premium — Custom + revisions")
        COMMERCIAL = "commercial", _("Commercial — Business / brand use")

    class Status(models.TextChoices):
        SUBMITTED = "submitted", _("Submitted")
        REVIEWING = "reviewing", _("Under Review")
        QUOTED = "quoted", _("Quoted")
        DEPOSIT_PAID = "deposit_paid", _("Deposit Paid")
        IN_PROGRESS = "in_progress", _("In Progress")
        PREVIEW_SENT = "preview_sent", _("Preview Sent")
        REVISION_REQUESTED = "revision_requested", _("Revision Requested")
        FINAL_PAYMENT_DUE = "final_payment_due", _("Final Payment Due")
        COMPLETED = "completed", _("Completed")
        CANCELLED = "cancelled", _("Cancelled")

    class IntendedUse(models.TextChoices):
        PERSONAL = "personal", _("Personal (wallpaper, print, etc.)")
        COMMERCIAL = "commercial", _("Commercial (merch, brand, album, etc.)")

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="commissions",
    )
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.BASIC)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.SUBMITTED,
        db_index=True,
    )

    # ── Request Details ───────────────────────────────────────────────────────
    title = models.CharField(
        max_length=200,
        help_text=_('Short title for the artwork, e.g. "Demon Skull with Initials"'),
    )
    description = models.TextField(
        help_text=_("Full description of what the customer wants"),
    )
    preferred_style = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('e.g. "Neon Graffiti", "Gothic", "Cyberpunk"'),
    )
    preferred_colors = models.CharField(
        max_length=200,
        blank=True,
        help_text=_("Preferred color palette"),
    )
    dimensions = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('e.g. "A4 portrait", "2000×2000px", "phone wallpaper"'),
    )
    intended_use = models.CharField(
        max_length=20,
        choices=IntendedUse.choices,
        default=IntendedUse.PERSONAL,
    )

    # ── Reference uploads (GitHub stored_path list stored as JSON) ────────────
    reference_images = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of GitHub stored_paths for reference images"),
    )
    sketch_upload_url = models.CharField(
        max_length=512,
        blank=True,
        help_text=_("GitHub stored_path for an uploaded sketch"),
    )

    # ── Pricing ───────────────────────────────────────────────────────────────
    quoted_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Price quoted by the artist (KES)"),
    )
    deposit_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Deposit required (typically 50% of quoted price)"),
    )
    final_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Remaining balance after deposit"),
    )

    # ── Delivery ──────────────────────────────────────────────────────────────
    final_file_url = models.CharField(
        max_length=512,
        blank=True,
        help_text=_("GitHub stored_path for the final delivered file — released after final payment"),
    )

    # ── Admin ─────────────────────────────────────────────────────────────────
    admin_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = table_name("commissions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Commission: {self.title} by {self.client.get_full_name()} [{self.status}]"

    @property
    def display_price(self):
        return self.quoted_price or "—"

    def set_quote(self, quoted_price: float, deposit_pct: float = 0.5):
        """Set the quoted price and calculate deposit/final amounts."""
        from decimal import Decimal
        self.quoted_price = Decimal(str(quoted_price))
        self.deposit_amount = (self.quoted_price * Decimal(str(deposit_pct))).quantize(Decimal("0.01"))
        self.final_amount = self.quoted_price - self.deposit_amount
        self.status = self.Status.QUOTED
        self.save(update_fields=["quoted_price", "deposit_amount", "final_amount", "status"])


class CommissionRevision(models.Model):
    """A preview/revision cycle within a commission."""

    class ClientResponse(models.TextChoices):
        PENDING = "pending", _("Awaiting Response")
        APPROVED = "approved", _("Approved")
        REVISION_REQUESTED = "revision_requested", _("Revision Requested")

    commission = models.ForeignKey(
        Commission,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    revision_number = models.PositiveSmallIntegerField(default=1)
    artist_notes = models.TextField(
        blank=True,
        help_text=_("Notes from the artist about this revision"),
    )
    preview_url = models.CharField(
        max_length=512,
        blank=True,
        help_text=_("GitHub stored_path for watermarked preview image"),
    )
    client_response = models.CharField(
        max_length=30,
        choices=ClientResponse.choices,
        default=ClientResponse.PENDING,
    )
    client_notes = models.TextField(
        blank=True,
        help_text=_("Feedback from client for this revision"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = table_name("commission_revisions")
        ordering = ["revision_number"]

    def __str__(self):
        return f"Revision {self.revision_number} — {self.commission.title}"

    def get_preview_public_url(self):
        from services.github_storage import github_public_url
        return github_public_url(self.preview_url)


class CommissionMessage(models.Model):
    """
    Simple message thread between client and artist for a commission.
    """
    commission = models.ForeignKey(
        Commission,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="commission_messages",
    )
    message = models.TextField()
    attachment_url = models.CharField(
        max_length=512,
        blank=True,
        help_text=_("Optional GitHub stored_path for an image attachment"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = table_name("commission_messages")
        ordering = ["created_at"]

    def __str__(self):
        return f"Message on '{self.commission.title}' by {self.sender.get_full_name()}"
