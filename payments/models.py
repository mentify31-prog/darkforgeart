"""
payments/models.py

Payment model for DarkForge Art.
Paystack is the sole payment provider.

Table prefix: dfa_
"""
import os

from django.db import models
from django.utils.translation import gettext_lazy as _

from orders.models import Order


def table_name(base_name: str) -> str:
    prefix = os.getenv("DB_TABLE_PREFIX", "dfa_")
    return f"{prefix}{base_name}"


class Payment(models.Model):
    """
    Records a single payment attempt against an Order.
    Linked to Paystack via the reference field.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SUCCESS = "success", _("Success")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")

    class PaymentMethod(models.TextChoices):
        CARD = "card", _("Card")
        MOBILE_MONEY = "mobile_money", _("Mobile Money (M-Pesa)")
        BANK_TRANSFER = "bank_transfer", _("Bank Transfer")
        USSD = "ussd", _("USSD")
        OTHER = "other", _("Other")

    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="payment",
    )
    paystack_reference = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text=_("Amount in KES"),
    )
    currency = models.CharField(max_length=3, default="KES")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    payment_method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices,
        blank=True,
    )
    paystack_response = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Raw Paystack webhook/verify payload for audit trail"),
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = table_name("payments")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment {self.paystack_reference} - {self.status} ({self.amount} {self.currency})"

    @property
    def is_successful(self) -> bool:
        return self.status == self.Status.SUCCESS
