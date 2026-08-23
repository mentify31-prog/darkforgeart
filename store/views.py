"""
store/views.py

Shop views: product listing, product detail, cart management.
"""
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from django.views.decorators.cache import cache_page
from .models import Product, ProductVariant, ProductType


@cache_page(300)
def shop(request):
    """All active products, filterable by type."""
    products = Product.objects.filter(is_active=True).select_related(
        "artwork",
        "digital_detail",
        "physical_detail",
        "limited_detail",
        "license_detail",
    ).prefetch_related("artwork__process_images")

    product_type = request.GET.get("type")
    if product_type:
        products = products.filter(product_type=product_type)

    products = products.order_by("-created_at")

    context = {
        "products": products,
        "product_types": ProductType.choices,
        "selected_type": product_type,
        "page_title": "Shop - DarkForge Art",
        "meta_description": (
            "Buy dark graffiti art, digital downloads, apparel, "
            "limited editions and commercial licenses."
        ),
    }
    return render(request, "store/shop.html", context)


@cache_page(300)
def product_detail(request, slug):
    """Individual product page with purchase options."""
    product = get_object_or_404(
        Product.objects.filter(is_active=True).select_related(
            "artwork",
            "digital_detail",
            "physical_detail",
            "limited_detail",
            "license_detail",
        ).prefetch_related("artwork__process_images", "artwork__tags"),
        slug=slug,
    )

    variants = []
    if product.product_type == ProductType.PHYSICAL:
        physical = getattr(product, "physical_detail", None)
        if physical:
            variants = physical.variants.filter(stock_available=True)

    limited_detail = None
    if product.product_type == ProductType.LIMITED:
        limited_detail = getattr(product, "limited_detail", None)

    phys = getattr(product, "physical_detail", None)
    preview_url = phys.mockup_image_url if (phys and phys.mockup_image_url) else (product.artwork.get_preview_public_url() if product.artwork else "")
    mockup_images = phys.mockup_images if phys else []

    context = {
        "product": product,
        "artwork": product.artwork,
        "preview_url": preview_url,
        "mockup_images": mockup_images,
        "variants": variants,
        "limited_detail": limited_detail,
        "page_title": f"{product.title} - DarkForge Art",
        "meta_description": product.description[:160] if product.description else (
            f"{product.title} - available from DarkForge Art."
        ),
        "og_image": preview_url,
    }
    return render(request, "store/product_detail.html", context)


def cart(request):
    """View the current cart."""
    cart_data = request.session.get("cart", {})
    cart_items = []
    total = 0

    for key, item in cart_data.items():
        try:
            product = Product.objects.select_related("artwork").get(pk=item["product_id"])
        except Product.DoesNotExist:
            continue

        variant = None
        if item.get("variant_id"):
            try:
                variant = ProductVariant.objects.get(pk=item["variant_id"])
            except ProductVariant.DoesNotExist:
                pass

        unit_price = variant.effective_price if variant else product.price
        quantity = item.get("quantity", 1)
        subtotal = unit_price * quantity
        total += subtotal

        rate = getattr(settings, "USD_EXCHANGE_RATE", 130.0) or 130.0
        subtotal_usd = round(float(subtotal) / rate, 2)

        cart_items.append({
            "key": key,
            "product": product,
            "variant": variant,
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": subtotal,
            "subtotal_usd": subtotal_usd,
            "preview_url": product.preview_url,
        })

    total_usd = round(float(total) / (getattr(settings, "USD_EXCHANGE_RATE", 130.0) or 130.0), 2)

    context = {
        "cart_items": cart_items,
        "total": total,
        "total_usd": total_usd,
        "page_title": "Your Cart - DarkForge Art",
    }
    return render(request, "store/cart.html", context)


@require_POST
def add_to_cart(request, product_id):
    """Add a product (and optional variant) to the session cart."""
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    variant_id = request.POST.get("variant_id")
    quantity = max(1, int(request.POST.get("quantity", 1)))

    # For limited editions, check availability
    if product.product_type == ProductType.LIMITED:
        limited = getattr(product, "limited_detail", None)
        if limited and limited.is_sold_out:
            messages.error(request, "Sorry, this limited edition is sold out.")
            return redirect("store:product_detail", slug=product.slug)

    cart_data = request.session.get("cart", {})
    key = f"{product_id}_{variant_id or 'none'}"

    # Set exact quantity chosen by user
    cart_data[key] = {
        "product_id": product_id,
        "variant_id": int(variant_id) if variant_id else None,
        "quantity": quantity,
    }

    request.session["cart"] = cart_data
    request.session.modified = True

    messages.success(request, f'"{product.title}" added to your cart.')
    return redirect("store:cart")


@require_POST
def remove_from_cart(request, key):
    """Remove an item from the session cart by its cart key."""
    cart_data = request.session.get("cart", {})
    cart_data.pop(key, None)
    request.session["cart"] = cart_data
    request.session.modified = True
    messages.info(request, "Item removed from cart.")
    return redirect("store:cart")


@require_POST
def update_cart(request, key):
    """Update quantity for a cart item."""
    cart_data = request.session.get("cart", {})
    quantity = int(request.POST.get("quantity", 1))
    if key in cart_data:
        if quantity < 1:
            cart_data.pop(key)
        else:
            cart_data[key]["quantity"] = quantity
    request.session["cart"] = cart_data
    request.session.modified = True
    return redirect("store:cart")
