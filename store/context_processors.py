"""
store/context_processors.py

Injects cart item count into every template context.
Cart is stored in request.session as a dict: {product_id: {qty, variant_id, ...}}
"""


def cart_context(request):
    """Add cart count to every template."""
    cart = request.session.get("cart", {})
    cart_count = sum(item.get("quantity", 1) for item in cart.values())
    return {"cart_count": cart_count}
