"""
payments/views.py

Paystack payment flow for DarkForge Art:
1. InitiatePaymentView  — creates order + Paystack transaction
2. VerifyPaymentView    — Paystack callback URL, verifies transaction
3. PaystackWebhookView  — Paystack webhook, idempotent fulfillment trigger
"""
import hashlib
import hmac
import json
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from orders.models import Order, OrderItem, DigitalDelivery
from orders.utils import generate_order_number
from store.models import Product, ProductVariant, ProductType
from .models import Payment
from services.paystack import get_paystack_service
from services.email_service import (
    send_order_confirmation_email,
    send_digital_delivery_email,
)

logger = logging.getLogger("darkforge")


# ─── Helper: Build Order from Cart ────────────────────────────────────────────

def _build_order_from_cart(request, shipping_data: dict) -> Order | None:
    """
    Create an Order and OrderItems from the session cart.
    Returns the Order or None if cart is empty/invalid.
    """
    cart_data = request.session.get("cart", {})
    if not cart_data:
        return None

    total = 0
    line_items = []

    for key, item in cart_data.items():
        try:
            product = Product.objects.select_related(
                "physical_detail", "limited_detail"
            ).get(pk=item["product_id"], is_active=True)
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

        line_items.append({
            "product": product,
            "variant": variant,
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": subtotal,
        })

    if not line_items:
        return None

    order = Order.objects.create(
        user=request.user if request.user.is_authenticated else None,
        order_number=generate_order_number(),
        status=Order.Status.PENDING,
        total_amount=total,
        currency=settings.PAYSTACK_CURRENCY,
        shipping_name=shipping_data.get("name", ""),
        shipping_email=shipping_data.get("email", ""),
        shipping_address={
            "address1": shipping_data.get("address1", ""),
            "city": shipping_data.get("city", ""),
            "country_code": shipping_data.get("country_code", "KE"),
            "zip": shipping_data.get("zip", ""),
            "phone": shipping_data.get("phone", ""),
        },
    )

    for line in line_items:
        product = line["product"]
        fulfillment_type = {
            ProductType.DIGITAL: OrderItem.FulfillmentType.DIGITAL,
            ProductType.PHYSICAL: OrderItem.FulfillmentType.PHYSICAL,
            ProductType.LIMITED: OrderItem.FulfillmentType.LIMITED,
            ProductType.LICENSE: OrderItem.FulfillmentType.LICENSE,
        }.get(product.product_type, OrderItem.FulfillmentType.DIGITAL)

        OrderItem.objects.create(
            order=order,
            product=product,
            variant=line["variant"],
            quantity=line["quantity"],
            unit_price=line["unit_price"],
            subtotal=line["subtotal"],
            fulfillment_type=fulfillment_type,
        )

    return order


# ─── Initiate Payment ─────────────────────────────────────────────────────────

@require_POST
def initiate_payment(request):
    """
    POST /payments/initiate/
    Creates the order from cart, initializes Paystack transaction.
    """
    shipping_data = {
        "name": request.POST.get("name", "").strip(),
        "email": request.POST.get("email", "").strip(),
        "address1": request.POST.get("address1", "").strip(),
        "city": request.POST.get("city", "").strip(),
        "country_code": request.POST.get("country_code", "KE").strip(),
        "zip": request.POST.get("zip", "").strip(),
        "phone": request.POST.get("phone", "").strip(),
    }

    if not shipping_data["name"] or not shipping_data["email"]:
        messages.error(request, "Please provide your name and email to continue.")
        return redirect("orders:checkout")

    order = _build_order_from_cart(request, shipping_data)
    if not order:
        messages.error(request, "Your cart is empty.")
        return redirect("store:shop")

    # Generate Paystack reference
    reference = f"DFA-{uuid.uuid4().hex[:12].upper()}"

    # Create payment record
    Payment.objects.create(
        order=order,
        paystack_reference=reference,
        amount=order.total_amount,
        currency=order.currency,
        status=Payment.Status.PENDING,
    )

    # Initialize Paystack transaction (always use current site's dynamic callback URL)
    paystack = get_paystack_service()
    callback_url = request.build_absolute_uri(f"/payments/verify/{reference}/")
    amount_kobo = int(order.total_amount * 100)

    status_code, body = paystack.initialize(
        email=shipping_data["email"],
        amount_kobo=amount_kobo,
        reference=reference,
        callback_url=callback_url,
        metadata={
            "order_number": order.order_number,
            "order_id": order.pk,
            "customer_name": shipping_data["name"],
        },
        currency=settings.PAYSTACK_CURRENCY,
    )

    if status_code not in (200, 201) or not body.get("status"):
        logger.error("Paystack init failed: %s %s", status_code, body)
        order.delete()  # Roll back order — not yet paid
        messages.error(request, paystack.friendly_error(body, "Payment initialization failed."))
        return redirect("orders:checkout")

    # Clear cart from session and store order_number for confirmation
    request.session["cart"] = {}
    request.session["last_order_number"] = order.order_number
    request.session.modified = True

    # Redirect customer to Paystack hosted payment page
    authorization_url = body["data"]["authorization_url"]
    return redirect(authorization_url)


# ─── Verify Payment (Paystack Callback) ───────────────────────────────────────

def verify_payment(request, reference):
    """
    GET /payments/verify/<reference>/
    Paystack redirects the customer here after payment.
    Verify the transaction and mark order as paid.
    """
    payment = get_object_or_404(Payment, paystack_reference=reference)

    # Idempotent: already verified
    if payment.status == Payment.Status.SUCCESS:
        return redirect("orders:order_confirmation", order_number=payment.order.order_number)

    paystack = get_paystack_service()
    status_code, body = paystack.verify(reference)

    if status_code != 200 or body.get("data", {}).get("status") != "success":
        logger.warning("Paystack verify returned non-success: %s %s", status_code, body)
        messages.error(request, "Payment could not be confirmed. Please contact support.")
        return redirect("orders:checkout")

    _mark_payment_success(payment, body)
    return redirect("orders:order_confirmation", order_number=payment.order.order_number)


# ─── Paystack Webhook ─────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def paystack_webhook(request):
    """
    POST /payments/webhook/
    Paystack sends charge.success events here.
    HMAC-SHA512 validated. Idempotent.
    """
    raw_body = request.body
    signature = request.headers.get("X-Paystack-Signature", "")

    paystack = get_paystack_service()
    if not paystack.is_valid_signature(raw_body, signature):
        logger.warning("Invalid Paystack webhook signature.")
        return HttpResponse("Invalid signature", status=400)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return HttpResponse("Invalid JSON", status=400)

    event = payload.get("event")
    if event != "charge.success":
        return HttpResponse("Ignored", status=200)

    data = payload.get("data", {})
    reference = data.get("reference")
    if not reference:
        return HttpResponse("No reference", status=400)

    try:
        payment = Payment.objects.get(paystack_reference=reference)
    except Payment.DoesNotExist:
        logger.error("Webhook: payment not found for reference %s", reference)
        return HttpResponse("Not found", status=404)

    if payment.status == Payment.Status.SUCCESS:
        return HttpResponse("Already processed", status=200)

    _mark_payment_success(payment, payload)
    return HttpResponse("OK", status=200)


# ─── Post-Payment Fulfillment ──────────────────────────────────────────────────

def _mark_payment_success(payment: Payment, raw_response: dict):
    """Mark payment as successful and trigger fulfillment."""
    from django.utils import timezone

    payment.status = Payment.Status.SUCCESS
    payment.paid_at = timezone.now()
    payment.paystack_response = raw_response

    # Extract payment method from Paystack response
    channel = raw_response.get("data", {}).get("channel", "")
    if channel == "card":
        payment.payment_method = Payment.PaymentMethod.CARD
    elif channel in ("mobile_money", "mpesa"):
        payment.payment_method = Payment.PaymentMethod.MOBILE_MONEY
    elif channel == "bank_transfer":
        payment.payment_method = Payment.PaymentMethod.BANK_TRANSFER
    elif channel == "ussd":
        payment.payment_method = Payment.PaymentMethod.USSD

    payment.save(update_fields=["status", "paid_at", "paystack_response", "payment_method"])

    # Mark order as paid
    order = payment.order
    order.status = Order.Status.PAID
    order.save(update_fields=["status"])

    # Trigger post-payment actions
    send_order_confirmation_email(order)
    _fulfill_order(order)


def _fulfill_order(order: Order):
    """
    Post-payment fulfillment:
    - Digital: create DigitalDelivery, send download email
    - Physical: submit Printful/Printify order
    - Limited: increment edition count, create digital delivery if applicable
    """
    for item in order.items.select_related(
        "product__digital_detail",
        "product__physical_detail",
        "product__limited_detail",
    ).all():
        if item.fulfillment_type in (
            OrderItem.FulfillmentType.DIGITAL,
            OrderItem.FulfillmentType.LICENSE,
        ):
            _deliver_digital(order, item)

        elif item.fulfillment_type == OrderItem.FulfillmentType.LIMITED:
            limited = getattr(item.product, "limited_detail", None)
            if limited:
                limited.edition_sold = min(limited.edition_sold + item.quantity, limited.edition_size)
                limited.save(update_fields=["edition_sold"])
            if limited and limited.includes_digital:
                _deliver_digital(order, item)

        elif item.fulfillment_type == OrderItem.FulfillmentType.PHYSICAL:
            _submit_physical_fulfillment(order, item)


def _deliver_digital(order: Order, item: OrderItem):
    """Create a DigitalDelivery record and send download email."""
    delivery, created = DigitalDelivery.objects.get_or_create(order_item=item)
    if created:
        item.fulfillment_status = OrderItem.FulfillmentStatus.SENT
        item.save(update_fields=["fulfillment_status"])
        send_digital_delivery_email(order, delivery)


def _submit_physical_fulfillment(order: Order, item: OrderItem):
    """Submit a fulfillment order to Printful or Printify."""
    from fulfillment.models import FulfillmentOrder
    from store.models import FulfillmentProvider

    physical = getattr(item.product, "physical_detail", None)
    if not physical:
        logger.warning("Physical product %s has no physical_detail.", item.product_id)
        return

    provider_name = physical.fulfillment_provider

    if provider_name == FulfillmentProvider.PRINTFUL:
        from fulfillment.printful import PrintfulProvider
        provider = PrintfulProvider()
    else:
        from fulfillment.printify import PrintifyProvider
        provider = PrintifyProvider()

    # Get the artwork print file URL
    from services.github_storage import github_public_url
    artwork_file_url = github_public_url(item.product.artwork.final_url)
    if not artwork_file_url:
        logger.error("No final artwork URL for product %s.", item.product_id)
        return

    result = provider.create_order(
        order_item=item,
        shipping_address=order.shipping_address,
        artwork_file_url=artwork_file_url,
    )

    FulfillmentOrder.objects.create(
        order_item=item,
        provider=provider_name,
        external_order_id=result.get("external_order_id") or "",
        status=result.get("status", "failed"),
        raw_response=result.get("raw_response", {}),
    )

    if result.get("success"):
        item.fulfillment_status = OrderItem.FulfillmentStatus.SENT
        item.save(update_fields=["fulfillment_status"])
    else:
        logger.error(
            "Fulfillment order creation failed for item %s: %s",
            item.pk,
            result.get("error", "unknown"),
        )
