"""
orders/views.py

Checkout, order confirmation, digital download, and order detail views.
"""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from store.models import Product, ProductVariant, ProductType
from .models import Order, OrderItem, DigitalDelivery
from .utils import generate_order_number

logger = logging.getLogger("darkforge")


def checkout(request):
    """
    Checkout page — collect shipping info and display order summary.
    Passes the cart to the payment step.
    """
    cart_data = request.session.get("cart", {})
    if not cart_data:
        messages.info(request, "Your cart is empty.")
        return redirect("store:shop")

    cart_items = []
    total = 0
    requires_shipping = False

    for key, item in cart_data.items():
        try:
            product = Product.objects.select_related(
                "artwork", "physical_detail", "limited_detail"
            ).get(pk=item["product_id"])
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

        if product.product_type == ProductType.PHYSICAL:
            requires_shipping = True

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
        })

    rate = getattr(settings, "USD_EXCHANGE_RATE", 130.0) or 130.0
    total_usd = round(float(total) / rate, 2)

    context = {
        "cart_items": cart_items,
        "total": total,
        "total_usd": total_usd,
        "requires_shipping": requires_shipping,
        "PAYSTACK_PUBLIC_KEY": settings.PAYSTACK_PUBLIC_KEY,
        "page_title": "Checkout — DarkForge Art",
    }
    return render(request, "orders/checkout.html", context)


def order_confirmation(request, order_number):
    """
    Order confirmation page shown after successful payment.
    """
    order = get_object_or_404(Order, order_number=order_number)

    # Ensure only the purchasing customer can view (or no user if guest)
    if order.user and request.user.is_authenticated and order.user != request.user:
        if not request.user.is_admin:
            messages.error(request, "You do not have permission to view this order.")
            return redirect("gallery:home")

    context = {
        "order": order,
        "items": order.items.select_related("product__artwork").all(),
        "page_title": f"Order Confirmed — {order.order_number}",
    }
    return render(request, "orders/order_confirmation.html", context)


def download(request, token):
    """
    Secure digital file download.
    Validates token, checks expiry and download count, then streams the file from GitHub.
    """
    delivery = get_object_or_404(DigitalDelivery, download_token=token)

    if not delivery.is_valid:
        if delivery.is_expired:
            messages.error(request, "This download link has expired.")
        else:
            messages.error(request, "This download link has reached its download limit.")
        return redirect("gallery:home")

    order_item = delivery.order_item
    if not order_item.order.is_paid:
        messages.error(request, "This order has not been paid.")
        return redirect("gallery:home")

    # Get the protected file from GitHub
    product = order_item.product
    digital = getattr(product, "digital_detail", None)

    # Fallback: use linked artwork final_url if DigitalProduct record has no file_url
    file_url = None
    if digital and digital.file_url:
        file_url = digital.file_url
    elif product.artwork and product.artwork.final_url:
        file_url = product.artwork.final_url
        logger.warning("DigitalProduct.file_url missing for product %s, falling back to artwork.final_url", product.pk)

    if not file_url:
        logger.error("No downloadable file found for product %s (digital_detail=%s)", product.pk, digital)
        messages.error(request, "Download file not found. Please contact support.")
        return redirect("gallery:home")

    try:
        from services.github_storage import get_github_service
        github = get_github_service()
        file_bytes = github.download_file(file_url)
    except Exception as exc:
        logger.error("Download failed for token %s: %s", token, exc)
        messages.error(request, "Failed to retrieve your file. Please try again or contact support.")
        return redirect("gallery:home")

    # Record download
    delivery.record_download()

    # Build a clean filename for the browser
    if digital and digital.file_format:
        ext = digital.file_format.lower()
    else:
        ext = file_url.split(".")[-1].lower() if "." in file_url else "jpg"
    filename = f"DarkForgeArt_{product.artwork.slug}.{ext}"

    from django.http import HttpResponse
    response = HttpResponse(file_bytes, content_type="application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def order_detail(request, order_number):
    """Customer view of a single order."""
    order = get_object_or_404(Order, order_number=order_number)
    if order.user != request.user and not request.user.is_admin:
        messages.error(request, "You do not have permission to view this order.")
        return redirect("accounts:dashboard")

    items = order.items.select_related(
        "product__artwork", "variant"
    ).prefetch_related("digital_delivery").all()

    context = {
        "order": order,
        "items": items,
        "page_title": f"Order {order.order_number} — DarkForge Art",
    }
    return render(request, "orders/order_detail.html", context)


@login_required
def verify_order_payment(request, order_number):
    """
    Manual payment verification for an order if internet dropped during callback.
    Calls Paystack API to check if payment succeeded, and fulfills the order if so.
    """
    order = get_object_or_404(Order, order_number=order_number)
    if order.user != request.user and not request.user.is_admin:
        messages.error(request, "Permission denied.")
        return redirect("accounts:dashboard")

    if order.is_paid:
        messages.info(request, "This order is already marked as paid.")
        return redirect("orders:order_detail", order_number=order.order_number)

    from payments.models import Payment
    payment = Payment.objects.filter(order=order).first()

    if not payment:
        messages.error(request, "No payment record found for this order.")
        return redirect("orders:order_detail", order_number=order.order_number)

    from services.paystack import get_paystack_service
    from payments.views import _mark_payment_success

    paystack = get_paystack_service()
    status_code, body = paystack.verify(payment.paystack_reference)

    if status_code == 200 and body.get("data", {}).get("status") == "success":
        _mark_payment_success(payment, body)
        messages.success(request, "Payment verified successfully! Your digital download links are ready below.")
    else:
        messages.error(request, "Paystack returned pending/unconfirmed status. If your account was debited, please contact support.")

    return redirect("orders:order_detail", order_number=order.order_number)
