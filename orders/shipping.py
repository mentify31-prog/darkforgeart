"""
orders/shipping.py

Calculates shipping fees for cart items based on destination country
and fulfillment provider (Printful vs Printify).
"""

from __future__ import annotations
import logging
from typing import Any
from django.conf import settings

logger = logging.getLogger("darkforge")

TIER1_FREE_COUNTRIES = {
    "US", "GB", "CA", "DE", "FR", "ES", "IT", "NL", "BE", "SE", "NO", "DK", "FI", "IE", "AT", "CH", "PL", "PT"
}
AUSTRALIA_NZ = {"AU", "NZ"}
PRINTIFY_SHIPPING_METHOD_PRIORITY = ("standard", "economy", "priority", "express", "printify_express")


def _printify_amount_usd(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return round(float(value) / 100, 2)
    if isinstance(value, str) and value.strip().isdigit():
        return round(float(value) / 100, 2)
    return None


def _printify_address_payload(shipping_address: dict[str, Any], country_code: str) -> dict[str, str]:
    name_parts = (shipping_address.get("name") or "").split()
    return {
        "first_name": name_parts[0] if name_parts else "Customer",
        "last_name": " ".join(name_parts[1:]) if len(name_parts) > 1 else "",
        "email": shipping_address.get("email") or "customer@example.com",
        "phone": shipping_address.get("phone") or "",
        "country": country_code,
        "region": shipping_address.get("region") or "",
        "address1": shipping_address.get("address1") or "",
        "address2": shipping_address.get("address2") or "",
        "city": shipping_address.get("city") or "",
        "zip": shipping_address.get("zip") or "",
    }


def _calculate_printify_actual_shipping_usd(
    printify_items: list[dict[str, Any]],
    shipping_address: dict[str, Any],
    country_code: str,
) -> float | None:
    line_items = []
    for item in printify_items:
        product = item["product"]
        variant = item.get("variant")
        physical = getattr(product, "physical_detail", None)
        if not physical or not physical.printify_product_id or not variant or not variant.printify_variant_id:
            return None
        line_items.append({
            "product_id": physical.printify_product_id,
            "variant_id": int(variant.printify_variant_id),
            "quantity": item.get("quantity", 1),
            "external_id": f"cart-{product.pk}-{variant.pk}",
        })

    if not line_items:
        return 0.0

    try:
        from fulfillment.printify import PrintifyProvider
        provider = PrintifyProvider()
        rates = provider.calculate_order_shipping(
            line_items=line_items,
            address_to=_printify_address_payload(shipping_address, country_code),
        )
    except Exception:
        logger.exception("Printify shipping calculation failed.")
        return None

    for method in PRINTIFY_SHIPPING_METHOD_PRIORITY:
        amount_usd = _printify_amount_usd(rates.get(method))
        if amount_usd is not None:
            return amount_usd
    return None


def calculate_cart_shipping(
    cart_items: list[dict[str, Any]],
    country_code: str = "US",
    shipping_address: dict[str, Any] | None = None,
) -> tuple[float, float, str]:
    """
    Calculate additional regional shipping surcharge in USD and KES based on destination country
    and fulfillment provider (Printful vs Printify).

    Printful items:
      - US, GB, CA, EU: $0.00 (Free Shipping)
      - AU, NZ: +$24.99 USD
      - Rest of World / Japan / Brazil / Africa: +$38.99 USD

    Printify items:
      - Product prices include a baseline shipping buffer.
      - When a full checkout address is available, charge only the extra amount above that buffer.
      - Fall back to the existing region surcharge if the live Printify API cannot quote the cart.

    Returns:
      (shipping_usd, shipping_kes, shipping_label)
    """
    c_code = (country_code or "US").upper().strip()
    rate = getattr(settings, "USD_EXCHANGE_RATE", 130.0) or 130.0

    total_shipping_usd = 0.0
    has_physical = False
    has_printful = False
    has_printify = False
    printify_items = []
    printify_qty = 0

    for item in cart_items:
        product = item["product"]
        if product.product_type != "physical":
            continue

        has_physical = True
        phys = getattr(product, "physical_detail", None)
        provider = phys.fulfillment_provider if phys else "printify"
        qty = item.get("quantity", 1)

        if provider == "printful":
            has_printful = True
            if c_code in TIER1_FREE_COUNTRIES:
                fee = 0.0
            elif c_code in AUSTRALIA_NZ:
                fee = 24.99
            else:
                fee = 38.99
        else:  # Printify
            has_printify = True
            printify_items.append(item)
            printify_qty += qty
            fee = 0.0

        total_shipping_usd += (fee * qty)

    if has_printify:
        shipping_address = shipping_address or {}
        actual_printify_shipping = None
        if shipping_address.get("address1") or shipping_address.get("city") or shipping_address.get("zip"):
            actual_printify_shipping = _calculate_printify_actual_shipping_usd(
                printify_items,
                shipping_address,
                c_code,
            )

        if actual_printify_shipping is None:
            if c_code not in TIER1_FREE_COUNTRIES:
                total_shipping_usd += 5.99 * printify_qty
        else:
            included_shipping = float(getattr(settings, "PRINTIFY_INCLUDED_SHIPPING_USD", 9.99) or 9.99)
            total_shipping_usd += max(actual_printify_shipping - (included_shipping * printify_qty), 0.0)

    if not has_physical:
        return 0.0, 0.0, "FREE (Digital Download)"

    if total_shipping_usd == 0.0:
        return 0.0, 0.0, "FREE (Included)"

    shipping_kes = round(total_shipping_usd * rate, 2)
    label = f"+${total_shipping_usd:.2f} USD (Regional Delivery Surcharge)"
    return round(total_shipping_usd, 2), shipping_kes, label
