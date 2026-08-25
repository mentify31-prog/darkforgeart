"""
store/admin.py
"""
import logging
import threading

from django import forms
from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from django.core.management import call_command
from django.core.cache import cache
from django.db import close_old_connections
from django.utils.safestring import mark_safe
from .models import (
    Product,
    DigitalProduct,
    PhysicalProduct,
    ProductVariant,
    LimitedEdition,
    LicenseProduct,
    ProductType,
)
from .services import upload_product_mockup_files

logger = logging.getLogger("darkforge")


def _run_import_commands(command_names):
    close_old_connections()
    try:
        for command_name in command_names:
            call_command(command_name)
            close_old_connections()
    except Exception:
        logger.exception("Admin fulfillment import failed for commands: %s", ", ".join(command_names))
    finally:
        close_old_connections()


class DigitalProductInline(admin.StackedInline):
    model = DigitalProduct
    extra = 0


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result


class PhysicalProductAdminForm(forms.ModelForm):
    upload_extra_mockups = MultipleFileField(
        required=False,
        help_text="Select one or multiple mockup images (PNG/JPG) from your computer to upload directly to your GitHub repository and display in the product gallery carousel.",
    )
    delete_mockups = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Check any mockup images you wish to delete from this product, then click Save.",
    )

    class Meta:
        model = PhysicalProduct
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.mockup_images:
            choices = []
            for idx, url in enumerate(self.instance.mockup_images):
                filename = url.split("/")[-1]
                choices.append((url, f"Delete Image #{idx + 1} ({filename[:35]})"))
            self.fields["delete_mockups"].choices = choices
        else:
            self.fields["delete_mockups"].choices = []


class PhysicalProductInline(admin.StackedInline):
    model = PhysicalProduct
    form = PhysicalProductAdminForm
    extra = 0
    readonly_fields = ["mockup_gallery_display"]

    def mockup_gallery_display(self, obj):
        if not obj or not obj.mockup_images:
            return "No mockup images available."
        html = '<div style="display:flex;gap:10px;flex-wrap:wrap;margin:10px 0;">'
        for idx, url in enumerate(obj.mockup_images):
            html += f'''
            <div style="text-align:center;border:1px solid rgba(255,255,255,0.15);padding:6px;background:#1a1a1a;border-radius:4px;width:110px;">
                <img src="{url}" style="width:98px;height:98px;object-fit:cover;border-radius:2px;display:block;margin-bottom:4px;">
                <span style="font-size:10px;color:#888;display:block;">#{idx + 1}</span>
            </div>
            '''
        html += '</div>'
        return mark_safe(html)

    mockup_gallery_display.short_description = "Current Product Mockup Gallery"


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
    form = PhysicalProductAdminForm
    list_display = ["product", "fulfillment_provider", "printful_product_id", "printify_product_id"]
    inlines = [PhysicalProductVariantInline]
    readonly_fields = ["mockup_gallery_display"]

    def mockup_gallery_display(self, obj):
        if not obj or not obj.mockup_images:
            return "No mockup images available."
        html = '<div style="display:flex;gap:10px;flex-wrap:wrap;margin:10px 0;">'
        for idx, url in enumerate(obj.mockup_images):
            html += f'''
            <div style="text-align:center;border:1px solid rgba(255,255,255,0.15);padding:6px;background:#1a1a1a;border-radius:4px;width:110px;">
                <img src="{url}" style="width:98px;height:98px;object-fit:cover;border-radius:2px;display:block;margin-bottom:4px;">
                <span style="font-size:10px;color:#888;display:block;">#{idx + 1}</span>
            </div>
            '''
        html += '</div>'
        return mark_safe(html)

    mockup_gallery_display.short_description = "Current Product Mockup Gallery"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        # 1. Handle mockup deletion
        delete_urls = form.cleaned_data.get("delete_mockups")
        if delete_urls:
            current = list(obj.mockup_images or [])
            obj.mockup_images = [u for u in current if u not in delete_urls]
            if obj.mockup_image_url in delete_urls:
                obj.mockup_image_url = obj.mockup_images[0] if obj.mockup_images else ""
            obj.save(update_fields=["mockup_images", "mockup_image_url"])
            self.message_user(request, f"Removed {len(delete_urls)} mockup image(s).", messages.SUCCESS)

        # 2. Handle new mockup uploads
        files = request.FILES.getlist("upload_extra_mockups")
        if files:
            urls = upload_product_mockup_files(obj, files)
            if urls:
                self.message_user(
                    request,
                    f"Successfully uploaded {len(urls)} custom mockup image(s) to GitHub repository and added to product!",
                    messages.SUCCESS,
                )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    show_full_result_count = False
    raw_id_fields = ["artwork"]
    list_display = [
        "title",
        "product_type",
        "price",
        "currency",
        "is_active",
        "show_in_gallery",
        "gallery_sort_order",
        "created_at",
    ]
    list_editable = ["show_in_gallery", "gallery_sort_order"]
    list_filter = ["product_type", "is_active", "show_in_gallery", "currency"]
    search_fields = ["title", "description", "artwork__title"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["created_at", "updated_at"]
    actions = [
        "show_selected_in_gallery",
        "hide_selected_from_gallery",
        "sync_from_printify",
        "sync_from_printful",
        "sync_all_fulfillment",
    ]

    fieldsets = (
        (None, {
            "fields": (
                "artwork",
                "product_type",
                "title",
                "slug",
                "description",
                "price",
                "currency",
                "is_active",
            )
        }),
        ("Gallery Feature", {
            "fields": ("show_in_gallery", "gallery_sort_order"),
            "description": "Use this to show selected active physical products on the Gallery page.",
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        cache.clear()

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
        self._start_import_commands(request, ("import_printify",), "Printify")
        return redirect("admin:store_product_changelist")

    def admin_import_printful(self, request):
        self._start_import_commands(request, ("import_printful",), "Printful")
        return redirect("admin:store_product_changelist")

    def _start_import_commands(self, request, command_names, label):
        thread = threading.Thread(
            target=_run_import_commands,
            args=(command_names,),
            name=f"{label.lower()}-fulfillment-import",
            daemon=True,
        )
        thread.start()
        self.message_user(
            request,
            f"{label} sync started in the background. Check Render logs for completion or errors.",
            messages.INFO,
        )

    @admin.action(description="Sync / Import all products from Printify")
    def sync_from_printify(self, request, queryset=None):
        return self.admin_import_printify(request)

    @admin.action(description="Sync / Import all products from Printful")
    def sync_from_printful(self, request, queryset=None):
        return self.admin_import_printful(request)

    @admin.action(description="Sync / Import from BOTH Printify & Printful")
    def sync_all_fulfillment(self, request, queryset=None):
        self._start_import_commands(request, ("import_printify", "import_printful"), "Printify and Printful")
        return redirect("admin:store_product_changelist")

    @admin.action(description="Show selected physical products in Gallery")
    def show_selected_in_gallery(self, request, queryset):
        updated = queryset.filter(product_type=ProductType.PHYSICAL).update(show_in_gallery=True)
        cache.clear()
        self.message_user(request, f"{updated} physical product(s) marked for the Gallery page.", messages.SUCCESS)

    @admin.action(description="Hide selected products from Gallery")
    def hide_selected_from_gallery(self, request, queryset):
        updated = queryset.update(show_in_gallery=False)
        cache.clear()
        self.message_user(request, f"{updated} product(s) hidden from the Gallery page.", messages.SUCCESS)

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

    def save_formset(self, request, form, formset, change):
        instances = formset.save()
        for instance in instances:
            if isinstance(instance, PhysicalProduct):
                prefix = formset.prefix
                
                # Check for deletions
                delete_urls = request.POST.getlist(f"{prefix}-0-delete_mockups")
                if not delete_urls:
                    delete_urls = request.POST.getlist("delete_mockups")
                if delete_urls:
                    current = list(instance.mockup_images or [])
                    instance.mockup_images = [u for u in current if u not in delete_urls]
                    if instance.mockup_image_url in delete_urls:
                        instance.mockup_image_url = instance.mockup_images[0] if instance.mockup_images else ""
                    instance.save(update_fields=["mockup_images", "mockup_image_url"])
                    self.message_user(request, f"Removed {len(delete_urls)} mockup image(s).", messages.SUCCESS)

                # Check for new file uploads
                files = request.FILES.getlist(f"{prefix}-0-upload_extra_mockups")
                if not files:
                    files = request.FILES.getlist("upload_extra_mockups")
                if files:
                    urls = upload_product_mockup_files(instance, files)
                    if urls:
                        self.message_user(
                            request,
                            f"Successfully uploaded {len(urls)} custom mockup image(s) to GitHub repository and added to product!",
                            messages.SUCCESS,
                        )
