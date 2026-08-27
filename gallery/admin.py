"""
gallery/admin.py

Django admin for Artwork, ArtworkImage, ArtworkTag.
Includes GitHub image upload handling via the admin form.
"""
import io

from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import Artwork, ArtworkImage, ArtworkTag
from store.models import Product


class ArtworkImageInline(admin.TabularInline):
    model = ArtworkImage
    extra = 1
    fields = ["step_label", "caption", "image_url", "order"]
    readonly_fields = []


class ArtworkAdminForm(forms.ModelForm):
    """
    Admin form that accepts file uploads and pushes them to GitHub.
    Also provides a multi-select widget to assign existing store products
    to this artwork.
    """
    upload_original = forms.FileField(required=False, label="Upload Original Pencil Scan")
    upload_colored = forms.FileField(required=False, label="Upload Colored Version")
    upload_final = forms.FileField(required=False, label="Upload Final Artwork (PROTECTED)")
    upload_preview = forms.FileField(required=False, label="Upload Preview Image")
    auto_generate_preview = forms.BooleanField(
        required=False,
        initial=True,
        label="Auto-watermark final file as preview (only if 'Upload Final Artwork' is provided)",
    )

    # ── Select existing products to assign to this artwork ─────────────────────
    linked_products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.filter(is_active=True).order_by("title"),
        required=False,
        label="Assign Store Products",
        help_text=(
            "Select existing products from your store to display on this artwork's page. "
            "Use Ctrl/Cmd+click to select multiple. Hold Shift to select a range."
        ),
        widget=forms.SelectMultiple(attrs={"size": "12", "style": "min-width:420px;"}),
    )

    class Meta:
        model = Artwork
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate with products currently assigned to this artwork
        if self.instance and self.instance.pk:
            self.fields["linked_products"].initial = Product.objects.filter(
                artwork=self.instance
            ).values_list("pk", flat=True)

    def save(self, commit=True):
        artwork = super().save(commit=False)
        from services.github_storage import get_github_service
        from services.watermark import create_preview_from_upload

        try:
            github = get_github_service()
        except ValueError:
            if commit:
                artwork.save()
                self.save_m2m()
                self._save_linked_products(artwork)
            return artwork

        slug = artwork.slug or artwork.title

        if self.cleaned_data.get("upload_original"):
            result = github.upload_file(
                self.cleaned_data["upload_original"],
                subdir="originals",
                filename_prefix=slug,
            )
            if result:
                artwork.original_pencil_url = result.stored_path

        if self.cleaned_data.get("upload_colored"):
            result = github.upload_file(
                self.cleaned_data["upload_colored"],
                subdir="colored",
                filename_prefix=slug,
            )
            if result:
                artwork.colored_url = result.stored_path

        if self.cleaned_data.get("upload_final"):
            final_file = self.cleaned_data["upload_final"]
            result = github.upload_file(final_file, subdir="finals", filename_prefix=slug)
            if result:
                artwork.final_url = result.stored_path

            if self.cleaned_data.get("auto_generate_preview"):
                final_file.seek(0)
                preview_bytes = create_preview_from_upload(final_file, slug=slug, style=artwork.style)
                if preview_bytes:
                    preview_file = io.BytesIO(preview_bytes)
                    preview_file.name = f"{slug}_preview.jpg"
                    prev_result = github.upload_file(
                        preview_file,
                        subdir="previews",
                        filename_prefix=slug,
                    )
                    if prev_result:
                        artwork.preview_url = prev_result.stored_path

        if self.cleaned_data.get("upload_preview"):
            result = github.upload_file(
                self.cleaned_data["upload_preview"],
                subdir="previews",
                filename_prefix=slug,
            )
            if result:
                artwork.preview_url = result.stored_path

        if commit:
            artwork.save()
            self.save_m2m()
            self._save_linked_products(artwork)
        return artwork

    def _save_linked_products(self, artwork):
        """
        Assign the selected products to this artwork (set artwork FK).
        Deselected products that were previously assigned are unlinked.
        """
        selected = set(self.cleaned_data.get("linked_products", []))
        selected_pks = {p.pk for p in selected}

        # Unlink products that were previously assigned but are no longer selected
        Product.objects.filter(artwork=artwork).exclude(pk__in=selected_pks).update(artwork=None)

        # Link newly selected products
        if selected_pks:
            Product.objects.filter(pk__in=selected_pks).update(artwork=artwork)


@admin.register(Artwork)
class ArtworkAdmin(admin.ModelAdmin):
    form = ArtworkAdminForm
    show_full_result_count = False
    list_display = [
        "title", "style", "artwork_type", "is_published", "is_featured",
        "preview_thumb", "product_count", "created_at",
    ]
    list_filter = ["style", "artwork_type", "is_published", "is_featured"]
    search_fields = ["title", "description"]
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ["tags"]
    readonly_fields = ["created_at", "updated_at", "final_url_warning"]
    inlines = [ArtworkImageInline]

    fieldsets = (
        ("Artwork Info", {
            "fields": ("title", "slug", "description", "story", "style", "artwork_type", "tags"),
        }),
        ("Publication", {
            "fields": ("is_published", "is_featured"),
        }),
        ("Linked Store Products", {
            "fields": ("linked_products",),
            "description": (
                "Select existing products from your store to show on this artwork's page. "
                "Ctrl/Cmd+click to select multiple."
            ),
        }),
        ("Image Uploads", {
            "fields": (
                "upload_original", "upload_colored",
                "upload_final", "auto_generate_preview", "upload_preview",
            ),
            "description": "Upload images to GitHub storage. Existing paths are preserved if no new file is uploaded.",
        }),
        ("Stored GitHub Paths (read-only editing)", {
            "fields": ("original_pencil_url", "colored_url", "preview_url"),
            "classes": ("collapse",),
        }),
        ("Protected Final File", {
            "fields": ("final_url_warning", "final_url"),
            "classes": ("collapse",),
            "description": "⚠ final_url is the full-resolution file. It is NEVER exposed publicly.",
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def preview_thumb(self, obj):
        url = obj.get_preview_public_url()
        if url:
            return format_html('<img src="{}" style="height:50px;border-radius:4px;" />', url)
        return " - "
    preview_thumb.short_description = "Preview"

    def product_count(self, obj):
        count = Product.objects.filter(artwork=obj).count()
        return count if count else "-"
    product_count.short_description = "Products"

    def final_url_warning(self, obj):
        return format_html(
            '<span style="color:red;font-weight:bold;">'
            "⚠ This path is protected. It is ONLY served via signed download URL after payment. "
            "Never share this URL directly."
            "</span>"
        )
    final_url_warning.short_description = "Security Warning"


@admin.register(ArtworkTag)
class ArtworkTagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
