"""
gallery/admin.py

Django admin for Artwork, ArtworkImage, ArtworkTag.
Includes GitHub image upload handling via the admin form.
"""
import io

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import Artwork, ArtworkImage, ArtworkTag
from store.models import Product


class ProductThumbnailWidget(forms.Widget):
    """
    Renders each active product as a clickable visual card with its mockup
    image, name, type and price — entirely server-side, no DOM transformation.
    JS only handles the click-to-toggle behaviour.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._products = []

    def set_products(self, products):
        self._products = list(products)

    def value_from_datadict(self, data, files, name):
        return data.getlist(name)

    def render(self, name, value, attrs=None, renderer=None):
        selected_pks = {str(v) for v in (value or [])}

        cards_html = ""
        for product in self._products:
            pk = str(product.pk)
            checked = "checked" if pk in selected_pks else ""
            selected_cls = "selected" if pk in selected_pks else ""

            phys = getattr(product, "physical_detail", None)
            if phys and getattr(phys, "mockup_image_url", ""):
                img_url = phys.mockup_image_url
            elif product.artwork:
                img_url = product.artwork.get_preview_public_url() or ""
            else:
                img_url = ""

            title = product.title
            ptype = product.get_product_type_display()
            price = f"${product.price_usd:.2f}"

            if img_url:
                media = f'<img src="{img_url}" alt="{title}" loading="lazy">'
            else:
                media = '<div class="pti-no-img">📷</div>'

            cards_html += (
                f'<label class="pti-card {selected_cls}" title="{title}">'
                f'<input type="checkbox" name="{name}" value="{pk}" {checked} style="display:none">'
                f'{media}'
                f'<div class="pti-info">'
                f'<div class="pti-name">{title}</div>'
                f'<div class="pti-meta">{ptype} · {price}</div>'
                f'</div>'
                f'</label>'
            )

        count = len(selected_pks)
        html = f"""
<style>
/* Override Django Admin's narrow floated field containers */
.field-linked_products {{
    clear: both !important;
    width: 100% !important;
    max-width: 100% !important;
    display: block !important;
    box-sizing: border-box !important;
    float: none !important;
}}
.field-linked_products > div {{
    width: 100% !important;
    max-width: 100% !important;
    display: block !important;
    clear: both !important;
    box-sizing: border-box !important;
    float: none !important;
}}
.field-linked_products label:first-child {{
    float: none !important;
    display: block !important;
    width: 100% !important;
    margin-bottom: 6px !important;
}}
.pti-wrapper {{
    border: 1px solid #333;
    border-radius: 6px;
    background: #141414;
    padding: 10px;
    width: 100% !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
    clear: both !important;
    display: block !important;
}}
.pti-summary {{
    cursor: pointer;
    font-weight: 600;
    color: #eee;
    font-size: 0.85rem;
    user-select: none;
    outline: none;
}}
.pti-scroll-box {{
    max-height: 380px;
    overflow-y: auto;
    margin-top: 10px;
    padding: 8px;
    border: 1px solid #282828;
    border-radius: 4px;
    background: #0d0d0d;
    width: 100% !important;
    box-sizing: border-box !important;
}}
.pti-scroll-box::-webkit-scrollbar {{
    width: 6px;
}}
.pti-scroll-box::-webkit-scrollbar-thumb {{
    background: #444;
    border-radius: 3px;
}}
.pti-grid {{
    display: grid !important;
    grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)) !important;
    gap: 8px !important;
    width: 100% !important;
    box-sizing: border-box !important;
}}
.pti-card {{
    border: 1px solid #333;
    border-radius: 5px;
    overflow: hidden;
    cursor: pointer;
    background: #1a1a1a;
    display: flex !important;
    flex-direction: column !important;
    text-decoration: none;
    transition: all .15s ease;
    box-sizing: border-box !important;
    width: 100% !important;
    margin: 0 !important;
}}
.pti-card:hover {{
    border-color: #777;
}}
.pti-card.selected {{
    border-color: #d90429;
    background: #2a0a0f;
    box-shadow: 0 0 0 1px #d90429;
}}
.pti-card img {{
    width: 100% !important;
    height: auto !important;
    aspect-ratio: 1 / 1 !important;
    object-fit: cover !important;
    display: block !important;
    background: #111;
}}
.pti-no-img {{
    width: 100% !important;
    aspect-ratio: 1 / 1 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    font-size: 1.2rem;
    background: #111;
    color: #666;
}}
.pti-info {{
    padding: 4px 6px;
    display: flex;
    flex-direction: column;
    gap: 2px;
}}
.pti-name {{
    font-size: 0.65rem;
    font-weight: 600;
    color: #ddd;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.pti-meta {{
    font-size: 0.60rem;
    color: #888;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
</style>
<details class="pti-wrapper" open>
  <summary class="pti-summary">
    Linked Store Products (<span id="pti-count-{name}">{count}</span> selected)
  </summary>
  <div class="pti-scroll-box">
    <div class="pti-grid" id="pti-grid-{name}">{cards_html}</div>
  </div>
</details>
<script>
(function(){{
  var grid = document.getElementById('pti-grid-{name}');
  var countEl = document.getElementById('pti-count-{name}');
  if (!grid) return;
  grid.querySelectorAll('.pti-card').forEach(function(card){{
    card.addEventListener('click', function(e){{
      e.preventDefault();
      var cb = card.querySelector('input[type=checkbox]');
      cb.checked = !cb.checked;
      card.classList.toggle('selected', cb.checked);
      if (countEl) {{
        countEl.textContent = grid.querySelectorAll('.selected').length;
      }}
    }});
  }});
}})();
</script>
"""
        return mark_safe(html)




class ArtworkImageInline(admin.TabularInline):
    model = ArtworkImage
    extra = 1
    fields = ["step_label", "caption", "image_url", "order"]
    readonly_fields = []


class ArtworkAdminForm(forms.ModelForm):
    """
    Admin form with GitHub image upload handling and a visual thumbnail
    product selector to assign existing store products to this artwork.
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

    linked_products = forms.MultiValueField(
        fields=(),
        required=False,
        label="Assign Store Products",
        help_text="Click a product card to select/deselect it. Selected cards highlight red.",
    )

    class Meta:
        model = Artwork
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Build the widget with all active products pre-fetched
        products = list(
            Product.objects.filter(is_active=True)
            .select_related("physical_detail", "artwork")
            .order_by("title")
        )
        widget = ProductThumbnailWidget()
        widget.set_products(products)

        # Replace linked_products with a simple field backed by our custom widget
        initial_pks = []
        if self.instance and self.instance.pk:
            initial_pks = list(
                Product.objects.filter(artwork=self.instance).values_list("pk", flat=True)
            )

        self.fields["linked_products"] = forms.MultipleChoiceField(
            choices=[(str(p.pk), p.title) for p in products],
            required=False,
            label="Assign Store Products",
            help_text="Click a product card to select/deselect it. Selected cards highlight red.",
            widget=widget,
            initial=initial_pks,
        )
        self.initial["linked_products"] = [str(pk) for pk in initial_pks]

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
        """Set artwork FK on selected products; clear it on deselected ones."""
        selected_pks = {int(pk) for pk in self.cleaned_data.get("linked_products", []) if pk}
        Product.objects.filter(artwork=artwork).exclude(pk__in=selected_pks).update(artwork=None)
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
            "description": "Click a product card to select it. Selected cards highlight red. Hit Save when done.",
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
