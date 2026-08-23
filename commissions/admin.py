"""
commissions/admin.py
"""
from django.contrib import admin
from .models import Commission, CommissionRevision, CommissionMessage


class CommissionRevisionInline(admin.TabularInline):
    model = CommissionRevision
    extra = 0
    readonly_fields = ["revision_number", "preview_url", "client_response", "responded_at"]


class CommissionMessageInline(admin.TabularInline):
    model = CommissionMessage
    extra = 0
    readonly_fields = ["sender", "message", "created_at"]


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    show_full_result_count = False
    raw_id_fields = ["client"]
    list_display = ["title", "client", "tier", "status", "quoted_price", "created_at"]
    list_filter = ["status", "tier", "intended_use"]
    search_fields = ["title", "client__email", "client__first_name"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [CommissionRevisionInline, CommissionMessageInline]
