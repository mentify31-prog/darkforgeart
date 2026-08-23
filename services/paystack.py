"""
services/paystack.py

Thin wrapper around the Paystack REST API.
Framework-agnostic - no Django imports here.
Adapted from EduAI services/paystack_service.py.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

import requests


class PaystackService:
    """Thin wrapper around the Paystack REST API."""

    _session = requests.Session()
    base_url = "https://api.paystack.co"

    def __init__(self, secret_key: str, public_key: str = "", currency: str = "KES") -> None:
        self.secret_key = secret_key
        self.public_key = public_key
        self.currency = currency

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    def initialize(
        self,
        *,
        email: str,
        amount_kobo: int,
        reference: str,
        callback_url: str,
        metadata: dict[str, Any] | None = None,
        currency: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """
        Initiate a Paystack transaction.
        amount_kobo: amount in the smallest currency unit (KES kobo = cents * 100).
        Returns (status_code, body).
        """
        payload: dict[str, Any] = {
            "email": email,
            "amount": int(amount_kobo),
            "reference": reference,
            "callback_url": callback_url,
            "currency": currency or self.currency,
        }
        if metadata:
            payload["metadata"] = metadata

        try:
            resp = self._session.post(
                f"{self.base_url}/transaction/initialize",
                headers=self._headers(),
                json=payload,
                timeout=20,
            )
            return int(resp.status_code), resp.json() if resp.content else {}
        except Exception as exc:
            return 599, {"message": str(exc)}

    def verify(self, reference: str) -> tuple[int, dict[str, Any]]:
        """Verify a transaction by reference. Returns (status_code, body)."""
        try:
            resp = self._session.get(
                f"{self.base_url}/transaction/verify/{reference}",
                headers=self._headers(),
                timeout=20,
            )
            return int(resp.status_code), resp.json() if resp.content else {}
        except Exception as exc:
            return 599, {"message": str(exc)}

    def is_valid_signature(self, raw_body: bytes, signature: str | None) -> bool:
        """Verify the HMAC-SHA512 webhook signature from Paystack."""
        secret = self.secret_key or ""
        if not secret:
            return False
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def friendly_error(self, body: dict[str, Any] | None, fallback: str = "Payment failed.") -> str:
        if not isinstance(body, dict):
            return fallback
        message = str(body.get("message") or "").strip()
        code = str(body.get("code") or "").strip().lower()
        if code == "unsupported_currency":
            return (
                f"Currency '{self.currency}' is not enabled on this Paystack account. "
                "Set PAYSTACK_CURRENCY=KES in your .env and retry."
            )
        return message or fallback


def get_paystack_service() -> PaystackService:
    """Return a configured PaystackService from Django settings."""
    from django.conf import settings
    return PaystackService(
        secret_key=settings.PAYSTACK_SECRET_KEY,
        public_key=settings.PAYSTACK_PUBLIC_KEY,
        currency=getattr(settings, "PAYSTACK_CURRENCY", "KES"),
    )
