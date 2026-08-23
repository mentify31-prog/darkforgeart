"""
fulfillment/views.py

Webhook handlers for Printful and Printify fulfillment events.
Updates FulfillmentOrder status and sends shipping notifications.
"""
import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import FulfillmentOrder
from orders.models import OrderItem
from services.email_service import send_shipping_notification_email

logger = logging.getLogger("darkforge")


@csrf_exempt
@require_POST
def printful_webhook(request):
    """
    POST /fulfillment/printful/webhook/
    Handles Printful order status webhooks.
    Events we care about: package_shipped, order_updated
    """
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse("Invalid JSON", status=400)

    event_type = payload.get("type", "")
    data = payload.get("data", {})
    order_data = data.get("order", {})
    external_id = str(order_data.get("id", ""))

    if not external_id:
        return HttpResponse("No order ID", status=400)

    try:
        fulfillment_order = FulfillmentOrder.objects.select_related(
            "order_item__order"
        ).get(external_order_id=external_id, provider="printful")
    except FulfillmentOrder.DoesNotExist:
        logger.warning("Printful webhook: FulfillmentOrder not found for ID %s", external_id)
        return HttpResponse("Not found", status=404)

    if event_type == "package_shipped":
        shipments = order_data.get("shipments", [])
        if shipments:
            first = shipments[0]
            fulfillment_order.tracking_number = first.get("tracking_number", "")
            fulfillment_order.tracking_url = first.get("tracking_url", "")

        fulfillment_order.status = FulfillmentOrder.Status.SHIPPED
        fulfillment_order.save(update_fields=["status", "tracking_number", "tracking_url"])

        # Update order item
        item = fulfillment_order.order_item
        item.fulfillment_status = OrderItem.FulfillmentStatus.SHIPPED
        item.save(update_fields=["fulfillment_status"])

        # Notify customer
        send_shipping_notification_email(item.order, fulfillment_order)

    elif event_type == "order_updated":
        new_status = order_data.get("status", "").lower()
        status_map = {
            "inprocess": FulfillmentOrder.Status.PROCESSING,
            "partial": FulfillmentOrder.Status.PROCESSING,
            "fulfilled": FulfillmentOrder.Status.SHIPPED,
            "archived": FulfillmentOrder.Status.DELIVERED,
            "canceled": FulfillmentOrder.Status.CANCELLED,
        }
        if new_status in status_map:
            fulfillment_order.status = status_map[new_status]
            fulfillment_order.save(update_fields=["status"])

    return HttpResponse("OK", status=200)


@csrf_exempt
@require_POST
def printify_webhook(request):
    """
    POST /fulfillment/printify/webhook/
    Handles Printify order status webhooks.
    """
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse("Invalid JSON", status=400)

    event_type = payload.get("type", "")
    resource = payload.get("resource", {})
    external_id = str(resource.get("id", ""))

    if not external_id:
        return HttpResponse("No order ID", status=400)

    try:
        fulfillment_order = FulfillmentOrder.objects.select_related(
            "order_item__order"
        ).get(external_order_id=external_id, provider="printify")
    except FulfillmentOrder.DoesNotExist:
        logger.warning("Printify webhook: FulfillmentOrder not found for ID %s", external_id)
        return HttpResponse("Not found", status=404)

    if event_type == "order:shipment:created":
        shipment_data = resource.get("data", {})
        fulfillment_order.tracking_number = shipment_data.get("number", "")
        fulfillment_order.tracking_url = shipment_data.get("url", "")
        fulfillment_order.status = FulfillmentOrder.Status.SHIPPED
        fulfillment_order.save(update_fields=["status", "tracking_number", "tracking_url"])

        item = fulfillment_order.order_item
        item.fulfillment_status = OrderItem.FulfillmentStatus.SHIPPED
        item.save(update_fields=["fulfillment_status"])

        send_shipping_notification_email(item.order, fulfillment_order)

    return HttpResponse("OK", status=200)
