"""
fulfillment/printful.py

PrintfulProvider - implements FulfillmentProviderBase for Printful's REST API.
Docs: https://developers.printful.com/docs/
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

from .base import FulfillmentProviderBase

logger = logging.getLogger("darkforge")

PRINTFUL_BASE_URL = "https://api.printful.com"


class PrintfulProvider(FulfillmentProviderBase):
    """Printful fulfillment provider."""

    def __init__(self, api_key: str | None = None, store_id: str | None = None) -> None:
        self.api_key = api_key or getattr(settings, "PRINTFUL_API_KEY", "")
        self.store_id = store_id or getattr(settings, "PRINTFUL_STORE_ID", "")
        self.session = requests.Session()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.store_id:
            headers["X-PF-Store-Id"] = str(self.store_id)
        self.session.headers.update(headers)

    def _get(self, path: str, **kwargs) -> dict:
        url = f"{PRINTFUL_BASE_URL}/{path.lstrip('/')}"
        params = kwargs.pop("params", {})
        if self.store_id and "store_id" not in params:
            params["store_id"] = self.store_id
        resp = self.session.get(url, params=params, timeout=20, **kwargs)
        return resp.json() if resp.content else {}

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        resp = self.session.post(
            f"{PRINTFUL_BASE_URL}/{path.lstrip('/')}",
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
        Submit an order to Printful.
        order_item.variant must have printful_variant_id set.
        """
        variant = order_item.variant
        if not variant or not variant.printful_variant_id:
            return {
                "success": False,
                "error": "No Printful variant ID configured for this product variant.",
                "external_order_id": None,
                "raw_response": {},
            }

        payload = {
            "recipient": {
                "name": shipping_address.get("name", ""),
                "address1": shipping_address.get("address1", ""),
                "city": shipping_address.get("city", ""),
                "country_code": shipping_address.get("country_code", "KE"),
                "zip": shipping_address.get("zip", ""),
                "phone": shipping_address.get("phone", ""),
                "email": shipping_address.get("email", ""),
            },
            "items": [
                {
                    "variant_id": variant.printful_variant_id,
                    "quantity": order_item.quantity,
                    "files": [
                        {
                            "type": "default",
                            "url": artwork_file_url,
                        }
                    ],
                }
            ],
            "retail_costs": {
                "currency": "USD",
                "subtotal": str(order_item.subtotal),
            },
        }

        status_code, body = self._post("orders", payload)
        success = status_code in (200, 201)
        external_id = str(body.get("result", {}).get("id", "")) if success else None

        if not success:
            logger.error("Printful order creation failed: %s %s", status_code, body)

        return {
            "success": success,
            "external_order_id": external_id,
            "status": "submitted" if success else "failed",
            "raw_response": body,
        }

    def get_order_status(self, external_order_id: str) -> dict[str, Any]:
        body = self._get(f"orders/{external_order_id}")
        result = body.get("result", {})
        shipments = result.get("shipments", [])
        tracking_number = ""
        tracking_url = ""
        if shipments:
            first_shipment = shipments[0]
            tracking_number = first_shipment.get("tracking_number", "")
            tracking_url = first_shipment.get("tracking_url", "")

        status_map = {
            "draft": "pending",
            "pending": "pending",
            "inprocess": "processing",
            "onhold": "processing",
            "partial": "processing",
            "fulfilled": "shipped",
            "archived": "delivered",
            "canceled": "cancelled",
        }
        raw_status = result.get("status", "").lower()
        mapped_status = status_map.get(raw_status, raw_status)

        return {
            "status": mapped_status,
            "tracking_number": tracking_number,
            "tracking_url": tracking_url,
            "shipped_at": None,  # Printful doesn't always provide an explicit shipped_at
            "raw_response": body,
        }

    def cancel_order(self, external_order_id: str) -> bool:
        resp = self.session.delete(
            f"{PRINTFUL_BASE_URL}/orders/{external_order_id}",
            timeout=20,
        )
        return resp.status_code < 300

    def get_shipping_rates(self, items: list[dict], address: dict) -> list[dict[str, Any]]:
        payload = {
            "recipient": address,
            "items": items,
        }
        _status, body = self._post("shipping/rates", payload)
        rates = body.get("result", [])
        return [
            {
                "name": r.get("name", ""),
                "rate": r.get("rate", 0),
                "currency": r.get("currency", "USD"),
                "min_days": r.get("minDeliveryDays"),
                "max_days": r.get("maxDeliveryDays"),
            }
            for r in rates
        ]
