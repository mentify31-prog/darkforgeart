"""
fulfillment/printify.py

PrintifyProvider - implements FulfillmentProviderBase for Printify's REST API.
Docs: https://printify.com/printify-api/
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

from .base import FulfillmentProviderBase

logger = logging.getLogger("darkforge")

PRINTIFY_BASE_URL = "https://api.printify.com/v1"


class PrintifyProvider(FulfillmentProviderBase):
    """Printify fulfillment provider."""

    def __init__(self, api_key: str | None = None, shop_id: str | None = None) -> None:
        self.api_key = api_key or getattr(settings, "PRINTIFY_API_KEY", "")
        self.shop_id = shop_id or getattr(settings, "PRINTIFY_SHOP_ID", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def _get(self, path: str, **kwargs) -> dict:
        resp = self.session.get(
            f"{PRINTIFY_BASE_URL}/{path.lstrip('/')}",
            timeout=20,
            **kwargs,
        )
        return resp.json() if resp.content else {}

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        resp = self.session.post(
            f"{PRINTIFY_BASE_URL}/{path.lstrip('/')}",
            json=payload,
            timeout=30,
        )
        return resp.status_code, resp.json() if resp.content else {}

    def create_order(
        self,
        order_item,
        shipping_address: dict,
        artwork_file_url: str,
    ) -> dict[str, Any]:
        """
        Submit an order to Printify.
        order_item.variant must have printify_variant_id set.
        """
        variant = order_item.variant
        if not variant or not variant.printify_variant_id:
            return {
                "success": False,
                "error": "No Printify variant ID configured for this product variant.",
                "external_order_id": None,
                "raw_response": {},
            }

        payload = {
            "label": f"DFA-{order_item.order.order_number}",
            "line_items": [
                {
                    "product_id": order_item.product.physical_detail.printify_product_id,
                    "variant_id": int(variant.printify_variant_id),
                    "quantity": order_item.quantity,
                }
            ],
            "shipping_method": 1,  # 1 = standard; customer can specify at checkout
            "address_to": {
                "first_name": shipping_address.get("name", "").split()[0],
                "last_name": " ".join(shipping_address.get("name", "").split()[1:]),
                "email": shipping_address.get("email", ""),
                "phone": shipping_address.get("phone", ""),
                "country": shipping_address.get("country_code", "KE"),
                "region": shipping_address.get("region", ""),
                "address1": shipping_address.get("address1", ""),
                "city": shipping_address.get("city", ""),
                "zip": shipping_address.get("zip", ""),
            },
        }

        status_code, body = self._post(
            f"shops/{self.shop_id}/orders.json",
            payload,
        )
        success = status_code in (200, 201)
        external_id = str(body.get("id", "")) if success else None

        if not success:
            logger.error("Printify order creation failed: %s %s", status_code, body)

        return {
            "success": success,
            "external_order_id": external_id,
            "status": "submitted" if success else "failed",
            "raw_response": body,
        }

    def get_order_status(self, external_order_id: str) -> dict[str, Any]:
        body = self._get(f"shops/{self.shop_id}/orders/{external_order_id}.json")
        shipments = body.get("shipments", [])
        tracking_number = ""
        tracking_url = ""
        if shipments:
            first = shipments[0]
            tracking_number = first.get("number", "")
            tracking_url = first.get("url", "")

        status_map = {
            "pending": "pending",
            "sending-to-production": "processing",
            "in-production": "processing",
            "sent-to-production": "processing",
            "shipped": "shipped",
            "fulfilled": "delivered",
            "cancelled": "cancelled",
        }
        raw_status = body.get("status", "").lower()
        mapped_status = status_map.get(raw_status, raw_status)

        return {
            "status": mapped_status,
            "tracking_number": tracking_number,
            "tracking_url": tracking_url,
            "shipped_at": None,
            "raw_response": body,
        }

    def cancel_order(self, external_order_id: str) -> bool:
        resp = self.session.post(
            f"{PRINTIFY_BASE_URL}/shops/{self.shop_id}/orders/{external_order_id}/cancel.json",
            timeout=20,
        )
        return resp.status_code < 300

    def calculate_order_shipping(self, line_items: list[dict], address_to: dict) -> dict[str, Any]:
        """
        Calculate Printify shipping for shop products using the same IDs used for order creation.
        Returns the raw Printify response, e.g. {"standard": 1000, "economy": 399}.
        Amounts are returned by Printify in cents.
        """
        payload = {
            "line_items": line_items,
            "address_to": address_to,
        }
        status_code, body = self._post(
            f"shops/{self.shop_id}/orders/shipping.json",
            payload,
        )
        if status_code not in (200, 201):
            logger.warning("Printify shipping calculation failed: %s %s", status_code, body)
            return {}
        return body

    def get_shipping_rates(self, items: list[dict], address: dict) -> list[dict[str, Any]]:
        body = self.calculate_order_shipping(items, address)
        rates = []
        for method, amount in body.items():
            try:
                rates.append({"method": method, "amount_usd": float(amount) / 100})
            except (TypeError, ValueError):
                continue
        return rates
