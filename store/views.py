"""
store/views.py

Shop views: product listing, product detail, cart management.
"""
import csv
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from django.views.decorators.cache import cache_page
from .models import Product, ProductVariant, ProductType


GOOGLE_PRODUCT_CATEGORY_DEFAULT = "Home & Garden > Decor > Artwork > Posters, Prints, & Visual Artwork"

GOOGLE_PRODUCT_CATEGORY_RULES = (
    (
        ("sweatshirt", "hoodie"),
        "Apparel & Accessories > Clothing > Shirts & Tops",
    ),
    (
        ("shirt", "t-shirt", "tee", "tank top", "crop top"),
        "Apparel & Accessories > Clothing > Shirts & Tops",
    ),
    (
        ("jacket", "coat"),
        "Apparel & Accessories > Clothing > Outerwear > Coats & Jackets",
    ),
    (
        ("backpack",),
        "Luggage & Bags > Backpacks",
    ),
    (
        ("fanny pack", "waist bag", "belt bag"),
        "Luggage & Bags > Fanny Packs",
    ),
    (
        ("crossbody", "messenger bag", "sling bag"),
        "Luggage & Bags > Messenger Bags",
    ),
    (
        ("bag", "tote"),
        "Apparel & Accessories > Handbags, Wallets & Cases > Handbags",
    ),
    (
        ("poster", "print", "art print", "canvas", "wall art"),
        GOOGLE_PRODUCT_CATEGORY_DEFAULT,
    ),
)


def _normalize_feed_image_url(image_url, base_url):
    """Return an absolute HTTP(S) image URL, or an empty string if unusable."""
    image_url = (image_url or "").strip()
    if not image_url:
        return ""
    if image_url.startswith("/"):
        image_url = f"{base_url}{image_url}"
    parsed = urlparse(image_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return image_url


def _product_feed_image_url(product, base_url):
    """Resolve the best catalog-safe image URL for a product."""
    candidates = []
    phys = getattr(product, "physical_detail", None)
    if phys:
        candidates.append(getattr(phys, "mockup_image_url", ""))
        candidates.extend(getattr(phys, "mockup_images", []) or [])
    candidates.append(product.preview_url)

    for image_url in candidates:
        normalized = _normalize_feed_image_url(image_url, base_url)
        if normalized:
            return normalized
    return ""


def _google_product_category(product):
    text = f"{product.title or ''} {product.description or ''} {product.get_product_type_display()}".lower()
    for keywords, category in GOOGLE_PRODUCT_CATEGORY_RULES:
        if any(keyword in text for keyword in keywords):
            return category
    if product.product_type == ProductType.PHYSICAL:
        return "Apparel & Accessories > Clothing > Shirts & Tops"
    return GOOGLE_PRODUCT_CATEGORY_DEFAULT


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


def pinterest_catalog_feed(request, fmt="csv"):
    """
    Dynamically generates a Pinterest / Google Shopping Product Data Feed (CSV or XML format).
    Pinterest & Google fetch this URL to auto-publish Shoppable Product Pins.
    """
    base_url = getattr(settings, "BASE_URL", "https://darkforgeart.store").rstrip("/")
    if not base_url.startswith("http"):
        base_url = f"https://{base_url}"

    active_products = Product.objects.filter(is_active=True).select_related(
        "artwork", "physical_detail", "digital_detail"
    ).prefetch_related("physical_detail__variants")

    feed_items = []

    for prod in active_products:
        prod_link = f"{base_url}/shop/product/{prod.slug}/"

        # Pinterest rejects rows with blank or non-fetchable image_link values.
        img_url = _product_feed_image_url(prod, base_url)
        if not img_url:
            continue

        description = prod.description or f"High quality {prod.title} from DarkForge Art."
        clean_desc = description.replace("\n", " ").replace("\r", " ").strip()
        google_product_category = _google_product_category(prod)

        phys = getattr(prod, "physical_detail", None)
        variants = list(phys.variants.filter(stock_available=True)) if phys else []

        if variants:
            for v in variants:
                var_title = f"{prod.title}"
                specs = [s for s in (v.color, v.size) if s]
                if specs:
                    var_title += f" ({' / '.join(specs)})"

                v_price = v.effective_price_usd or prod.price_usd
                sku = f"{prod.slug}-v{v.pk}"

                feed_items.append({
                    "id": sku,
                    "item_group_id": prod.slug,
                    "title": var_title[:150],
                    "description": clean_desc[:9000],
                    "link": prod_link,
                    "image_link": img_url,
                    "price": f"{v_price:.2f} USD",
                    "availability": "in stock",
                    "condition": "new",
                    "brand": "DarkForge Art",
                    "google_product_category": google_product_category,
                })
        else:
            sku = prod.slug
            feed_items.append({
                "id": sku,
                "item_group_id": prod.slug,
                "title": prod.title[:150],
                "description": clean_desc[:9000],
                "link": prod_link,
                "image_link": img_url,
                "price": f"{prod.price_usd:.2f} USD",
                "availability": "in stock",
                "condition": "new",
                "brand": "DarkForge Art",
                "google_product_category": google_product_category,
            })

    if fmt == "xml":
        rss = ET.Element("rss", {"version": "2.0", "xmlns:g": "http://base.google.com/ns/1.0"})
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "DarkForge Art Product Feed"
        ET.SubElement(channel, "link").text = base_url
        ET.SubElement(channel, "description").text = "Shoppable product feed for DarkForge Art"

        for item in feed_items:
            item_elem = ET.SubElement(channel, "item")
            ET.SubElement(item_elem, "g:id").text = item["id"]
            ET.SubElement(item_elem, "g:item_group_id").text = item["item_group_id"]
            ET.SubElement(item_elem, "title").text = item["title"]
            ET.SubElement(item_elem, "description").text = item["description"]
            ET.SubElement(item_elem, "link").text = item["link"]
            ET.SubElement(item_elem, "g:image_link").text = item["image_link"]
            ET.SubElement(item_elem, "g:price").text = item["price"]
            ET.SubElement(item_elem, "g:availability").text = item["availability"]
            ET.SubElement(item_elem, "g:condition").text = item["condition"]
            ET.SubElement(item_elem, "g:brand").text = item["brand"]
            ET.SubElement(item_elem, "g:google_product_category").text = item["google_product_category"]

        xml_bytes = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
        return HttpResponse(xml_bytes, content_type="application/xml; charset=utf-8")

    # Default CSV format
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="pinterest_catalog.csv"'

    fieldnames = [
        "id", "item_group_id", "title", "description", "link",
        "image_link", "price", "availability", "condition", "brand", "google_product_category"
    ]
    writer = csv.DictWriter(response, fieldnames=fieldnames)
    writer.writeheader()
    for item in feed_items:
        writer.writerow(item)

    return response
