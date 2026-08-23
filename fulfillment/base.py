"""
fulfillment/base.py

Abstract FulfillmentProvider interface.
All POD providers (Printful, Printify) implement this interface.
This allows swapping providers without rebuilding the order system.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class FulfillmentProviderBase(ABC):
    """Abstract base class for all POD fulfillment providers."""

    @abstractmethod
    def create_order(
        self,
        order_item,
        shipping_address: dict,
        artwork_file_url: str,
    ) -> dict[str, Any]:
        """
        Submit a fulfillment order to the provider.

        Args:
            order_item: OrderItem model instance (has product.physical_detail.variant info).
            shipping_address: Dict with keys: name, address1, city, country_code, zip, phone.
            artwork_file_url: Public URL of the print file.

        Returns:
            Dict with at minimum: external_order_id, status, raw_response.
        """
        ...

    @abstractmethod
    def get_order_status(self, external_order_id: str) -> dict[str, Any]:
        """
        Fetch the current status of a fulfillment order.

        Returns:
            Dict with: status, tracking_number, tracking_url, shipped_at, raw_response.
        """
        ...

    @abstractmethod
    def cancel_order(self, external_order_id: str) -> bool:
        """
        Cancel a fulfillment order (only possible before printing starts).

        Returns:
            True if successfully cancelled, False otherwise.
        """
        ...

    @abstractmethod
    def get_shipping_rates(
        self,
        items: list[dict],
        address: dict,
    ) -> list[dict[str, Any]]:
        """
        Get available shipping rates for a list of items to an address.

        Returns:
            List of rate dicts: [{name, rate, currency, min_days, max_days}, ...]
        """
        ...
