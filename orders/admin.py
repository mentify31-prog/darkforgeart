"""
orders/admin.py
"""
from django.contrib import admin
from .models import Order, OrderItem, DigitalDelivery


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "variant", "quantity", "unit_price", "subtotal", "fulfillment_type", "fulfillment_status"]


class DigitalDeliveryInline(admin.StackedInline):
    model = DigitalDelivery
    extra = 0
    readonly_fields = ["download_token", "download_count", "expires_at", "first_downloaded_at", "last_downloaded_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    show_full_result_count = False
    raw_id_fields = ["user"]
    list_display = ["order_number", "shipping_name", "shipping_email", "status", "total_amount", "currency", "created_at"]
    list_filter = ["status", "currency"]
    search_fields = ["order_number", "shipping_name", "shipping_email"]
    readonly_fields = ["order_number", "created_at", "updated_at"]
    inlines = [OrderItemInline]


@admin.register(DigitalDelivery)
class DigitalDeliveryAdmin(admin.ModelAdmin):
    show_full_result_count = False
    raw_id_fields = ["order_item"]
    list_display = ["order_item", "download_token", "download_count", "max_downloads", "expires_at", "is_valid"]
    readonly_fields = ["download_token", "first_downloaded_at", "last_downloaded_at"]

    def is_valid(self, obj):
        return obj.is_valid
    is_valid.boolean = True
