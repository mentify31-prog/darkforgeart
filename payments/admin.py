"""
payments/admin.py
"""
from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    show_full_result_count = False
    raw_id_fields = ["order"]
    list_display = ["paystack_reference", "order", "amount", "currency", "status", "payment_method", "paid_at"]
    list_filter = ["status", "payment_method", "currency"]
    search_fields = ["paystack_reference", "order__order_number"]
    readonly_fields = ["paystack_reference", "paystack_response", "created_at", "updated_at"]
