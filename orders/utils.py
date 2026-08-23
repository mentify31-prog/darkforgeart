"""
orders/utils.py

Order number generation and signed download URL utilities.
"""
import secrets
from datetime import date


def generate_order_number() -> str:
    """
    Generate a unique order number in the format DFA-YYYY-XXXXXX.
    e.g. DFA-2026-004821
    """
    from .models import Order
    year = date.today().year
    # Use order count + random suffix for uniqueness
    count = Order.objects.filter(created_at__year=year).count() + 1
    suffix = secrets.randbelow(9000) + 1000  # 4-digit random component
    return f"DFA-{year}-{count:04d}{suffix % 100:02d}"
