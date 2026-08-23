"""
fulfillment/models.py

FulfillmentOrder - tracks a POD order placed with Printful or Printify.

Table prefix: dfa_
"""
import os

from django.db import models
from django.utils.translation import gettext_lazy as _

from orders.models import OrderItem


def table_name(base_name: str) -> str:
    prefix = os.getenv("DB_TABLE_PREFIX", "dfa_")
    return f"{prefix}{base_name}"


class FulfillmentProvider(models.TextChoices):
    PRINTFUL = "printful", _("Printful")
    PRINTIFY = "printify", _("Printify")


class FulfillmentOrder(models.Model):
    """
    Tracks a POD fulfillment order placed with Printful or Printify
    for a physical OrderItem.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SUBMITTED = "submitted", _("Submitted to Provider")
        PROCESSING = "processing", _("Processing")
        SHIPPED = "shipped", _("Shipped")
        DELIVERED = "delivered", _("Delivered")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Cancelled")

    order_item = models.OneToOneField(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="fulfillment_order",
    )
    provider = models.CharField(
        max_length=20,
        choices=FulfillmentProvider.choices,
    )
    external_order_id = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Order ID returned by Printful or Printify"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    tracking_number = models.CharField(max_length=200, blank=True)
    tracking_url = models.URLField(max_length=500, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)
    raw_response = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Raw provider API response for debugging"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = table_name("fulfillment_orders")
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Fulfillment {self.get_provider_display()} #{self.external_order_id or 'pending'} "
            f" - {self.status}"
        )
