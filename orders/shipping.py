"""
orders/shipping.py

Calculates shipping fees for cart items based on destination country
and fulfillment provider (Printful vs Printify).
"""

from __future__ import annotations
from typing import Any
from django.conf import settings

TIER1_FREE_COUNTRIES = {
    "US", "GB", "CA", "DE", "FR", "ES", "IT", "NL", "BE", "SE", "NO", "DK", "FI", "IE", "AT", "CH", "PL", "PT"
}
AUSTRALIA_NZ = {"AU", "NZ"}


def calculate_cart_shipping(cart_items: list[dict[str, Any]], country_code: str = "US") -> tuple[float, float, str]:
    """
    Calculate additional regional shipping surcharge in USD and KES based on destination country
    and fulfillment provider (Printful vs Printify).

    Printful items:
      - US, GB, CA, EU: $0.00 (Free Shipping)
      - AU, NZ: +$24.99 USD
      - Rest of World / Japan / Brazil / Africa: +$38.99 USD

    Printify items:
      - US, GB, CA, EU: $0.00 (Free Shipping)
      - Rest of World / Africa: +$5.99 USD

    Returns:
      (shipping_usd, shipping_kes, shipping_label)
    """
    c_code = (country_code or "US").upper().strip()
    rate = getattr(settings, "USD_EXCHANGE_RATE", 130.0) or 130.0

    total_shipping_usd = 0.0
    has_physical = False
    has_printful = False
    has_printify = False

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
            if c_code in TIER1_FREE_COUNTRIES:
                fee = 0.0
            else:
                fee = 5.99

        total_shipping_usd += (fee * qty)

    if not has_physical:
        return 0.0, 0.0, "FREE (Digital Download)"

    if total_shipping_usd == 0.0:
        return 0.0, 0.0, "FREE (Included)"

    shipping_kes = round(total_shipping_usd * rate, 2)
    label = f"+${total_shipping_usd:.2f} USD (Regional Delivery Surcharge)"
    return round(total_shipping_usd, 2), shipping_kes, label
