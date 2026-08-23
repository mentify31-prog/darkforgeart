"""
store/admin.py
"""
from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from django.core.management import call_command
from .models import (
    Product,
    DigitalProduct,
    PhysicalProduct,
    ProductVariant,
    LimitedEdition,
    LicenseProduct,
    ProductType,
)


class DigitalProductInline(admin.StackedInline):
    model = DigitalProduct
    extra = 0


class PhysicalProductInline(admin.StackedInline):
    model = PhysicalProduct
    extra = 0


class PhysicalProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


class LimitedEditionInline(admin.StackedInline):
    model = LimitedEdition
    extra = 0


class LicenseProductInline(admin.StackedInline):
    model = LicenseProduct
    extra = 0


@admin.register(PhysicalProduct)
class PhysicalProductAdmin(admin.ModelAdmin):
    list_display = ["product", "fulfillment_provider", "printful_product_id", "printify_product_id"]
    inlines = [PhysicalProductVariantInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    show_full_result_count = False
    raw_id_fields = ["artwork"]
    list_display = ["title", "product_type", "price", "currency", "is_active", "created_at"]
    list_filter = ["product_type", "is_active", "currency"]
    search_fields = ["title", "description", "artwork__title"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["created_at", "updated_at"]
    actions = ["sync_from_printify", "sync_from_printful", "sync_all_fulfillment"]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-printify/",
                self.admin_site.admin_view(self.admin_import_printify),
                name="store_product_import_printify",
            ),
            path(
                "import-printful/",
                self.admin_site.admin_view(self.admin_import_printful),
                name="store_product_import_printful",
            ),
        ]
        return custom_urls + urls

    def admin_import_printify(self, request):
        try:
            call_command("import_printify")
            self.message_user(request, "Printify products and variants imported successfully!", messages.SUCCESS)
        except Exception as exc:
            self.message_user(request, f"Printify sync error: {exc}", messages.ERROR)
        return redirect("admin:store_product_changelist")

    def admin_import_printful(self, request):
        try:
            call_command("import_printful")
            self.message_user(request, "Printful products and variants imported successfully!", messages.SUCCESS)
        except Exception as exc:
            self.message_user(request, f"Printful sync error: {exc}", messages.ERROR)
        return redirect("admin:store_product_changelist")

    @admin.action(description="Sync / Import all products from Printify")
    def sync_from_printify(self, request, queryset=None):
        return self.admin_import_printify(request)

    @admin.action(description="Sync / Import all products from Printful")
    def sync_from_printful(self, request, queryset=None):
        return self.admin_import_printful(request)

    @admin.action(description="Sync / Import from BOTH Printify & Printful")
    def sync_all_fulfillment(self, request, queryset=None):
        self.admin_import_printify(request)
        self.admin_import_printful(request)
        return redirect("admin:store_product_changelist")

    def get_inlines(self, request, obj=None):
        if obj is None:
            return [
                DigitalProductInline,
                PhysicalProductInline,
                LimitedEditionInline,
                LicenseProductInline,
            ]
        inline_map = {
            ProductType.DIGITAL: [DigitalProductInline],
            ProductType.PHYSICAL: [PhysicalProductInline],
            ProductType.LIMITED: [LimitedEditionInline],
            ProductType.LICENSE: [LicenseProductInline],
        }
        return inline_map.get(obj.product_type, [])
