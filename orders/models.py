"""
orders/models.py

Order, OrderItem, and DigitalDelivery models for DarkForge Art.

Table prefix: dfa_
"""
import os
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from store.models import Product, ProductVariant


def table_name(base_name: str) -> str:
    prefix = os.getenv("DB_TABLE_PREFIX", "dfa_")
    return f"{prefix}{base_name}"


class Order(models.Model):
    """
    A customer order. Can contain multiple OrderItems of mixed types.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        PROCESSING = "processing", _("Processing")
        FULFILLED = "fulfilled", _("Fulfilled")
        CANCELLED = "cancelled", _("Cancelled")
        REFUNDED = "refunded", _("Refunded")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    order_number = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        help_text=_('Auto-generated, e.g. "DFA-2026-001234"'),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")

    # Shipping / contact info (collected at checkout)
    shipping_name = models.CharField(max_length=200)
    shipping_email = models.EmailField()
    shipping_address = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Shipping address JSON — required for physical products"),
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = table_name("orders")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order_number} — {self.status}"

    @property
    def is_paid(self) -> bool:
        return self.status in (self.Status.PAID, self.Status.PROCESSING, self.Status.FULFILLED)

    def has_digital_items(self) -> bool:
        return self.items.filter(fulfillment_type="digital").exists()

    def has_physical_items(self) -> bool:
        return self.items.filter(fulfillment_type="physical").exists()


class OrderItem(models.Model):
    """A single line item within an Order."""

    class FulfillmentType(models.TextChoices):
        DIGITAL = "digital", _("Digital Download")
        PHYSICAL = "physical", _("Physical Product")
        LIMITED = "limited", _("Limited Edition")
        LICENSE = "license", _("Commercial License")

    class FulfillmentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        SENT = "sent", _("Sent / Download Ready")
        DOWNLOADED = "downloaded", _("Downloaded")
        SHIPPED = "shipped", _("Shipped")
        DELIVERED = "delivered", _("Delivered")

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    fulfillment_type = models.CharField(max_length=20, choices=FulfillmentType.choices)
    fulfillment_status = models.CharField(
        max_length=20,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.PENDING,
    )

    class Meta:
        db_table = table_name("order_items")

    def __str__(self):
        return f"{self.product.title} × {self.quantity} (Order {self.order.order_number})"

    def save(self, *args, **kwargs):
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)


class DigitalDelivery(models.Model):
    """
    Secure download record for a digital OrderItem.

    The download_token is a UUID sent in the download URL.
    expires_at is set when created (e.g. 7 days).
    After max_downloads, the link is invalidated.
    """
    order_item = models.OneToOneField(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="digital_delivery",
    )
    download_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    download_count = models.PositiveSmallIntegerField(default=0)
    max_downloads = models.PositiveSmallIntegerField(
        default=5,
        help_text=_("Maximum number of times the download link can be used"),
    )
    expires_at = models.DateTimeField(
        help_text=_("When the download link expires"),
    )
    first_downloaded_at = models.DateTimeField(null=True, blank=True)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = table_name("digital_deliveries")

    def __str__(self):
        return f"Download: {self.order_item} (used {self.download_count}/{self.max_downloads})"

    def save(self, *args, **kwargs):
        if not self.pk and not hasattr(self, '_expires_set'):
            from datetime import timedelta
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_exhausted(self) -> bool:
        return self.download_count >= self.max_downloads

    @property
    def is_valid(self) -> bool:
        return not self.is_expired and not self.is_exhausted

    def record_download(self):
        """Increment counter and track timestamps."""
        now = timezone.now()
        if not self.first_downloaded_at:
            self.first_downloaded_at = now
        self.last_downloaded_at = now
        self.download_count += 1
        self.save(update_fields=["download_count", "first_downloaded_at", "last_downloaded_at"])
