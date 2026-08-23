"""
fulfillment/admin.py
"""
from django.contrib import admin
from .models import FulfillmentOrder


@admin.register(FulfillmentOrder)
class FulfillmentOrderAdmin(admin.ModelAdmin):
    show_full_result_count = False
    raw_id_fields = ["order_item"]
    list_display = ["order_item", "provider", "external_order_id", "status", "tracking_number", "created_at"]
    list_filter = ["provider", "status"]
    search_fields = ["external_order_id", "order_item__order__order_number"]
    readonly_fields = ["raw_response", "created_at", "updated_at"]
