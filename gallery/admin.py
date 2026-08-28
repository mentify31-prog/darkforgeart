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


class ProductThumbnailWidget(forms.CheckboxSelectMultiple):
    """
    Checkbox widget that renders each product option with its mockup
    thumbnail so you can visually identify products when assigning them.
    """
    def optgroups(self, name, value, attrs=None):
        # Pre-fetch all products with their physical_detail in one query
        qs = self.choices.queryset.select_related("physical_detail", "artwork")
        self._product_map = {str(p.pk): p for p in qs}
        return super().optgroups(name, value, attrs)

    def create_option(self, name, value, label, selected, index, subgroup=None, attrs=None, subindex=None):
        option = super().create_option(name, value, label, selected, index, subgroup, attrs)
        pk = str(value)
        product = self._product_map.get(pk) if hasattr(self, "_product_map") else None
        if product:
            img_url = ""
            phys = getattr(product, "physical_detail", None)
            if phys and getattr(phys, "mockup_image_url", ""):
                img_url = phys.mockup_image_url
            elif product.artwork:
                img_url = product.artwork.get_preview_public_url()
            option["attrs"]["data-img"] = img_url
            option["attrs"]["data-type"] = product.get_product_type_display()
            option["attrs"]["data-price"] = f"${product.price_usd:.2f}"
        return option

    def render(self, name, value, attrs=None, renderer=None):
        # Render the standard checkboxes then inject JS to turn them into cards
        output = super().render(name, value, attrs, renderer)
        style = """
<style>
.product-thumb-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:10px; margin-top:8px; }
.product-thumb-item { border:2px solid #333; border-radius:6px; overflow:hidden; cursor:pointer; transition:border-color .15s; background:#1a1a1a; }
.product-thumb-item:hover { border-color:#888; }
.product-thumb-item.selected { border-color:#d90429; background:#2a0a0f; }
.product-thumb-item input[type=checkbox] { display:none; }
.product-thumb-item img { width:100%; aspect-ratio:1; object-fit:cover; display:block; background:#111; }
.product-thumb-item .no-img { width:100%; aspect-ratio:1; display:flex; align-items:center; justify-content:center; color:#555; font-size:2rem; background:#111; }
.product-thumb-item .info { padding:6px 8px; }
.product-thumb-item .info .pname { font-size:0.72rem; font-weight:600; color:#ddd; line-height:1.3; margin-bottom:2px; }
.product-thumb-item .info .pmeta { font-size:0.65rem; color:#888; }
.product-thumb-selected-count { margin-top:6px; font-size:0.8rem; color:#aaa; }
</style>
"""
        script = """
<script>
(function(){
  var wrap = document.getElementById('product-thumb-wrap');
  if(!wrap) return;
  // Django CheckboxSelectMultiple renders div > div > label > input, NOT ul > li
  var checkboxes = wrap.querySelectorAll('input[type=checkbox]');
  if(!checkboxes.length) return;
  var grid = document.createElement('div');
  grid.className = 'product-thumb-grid';
  var countEl = document.createElement('div');
  countEl.className = 'product-thumb-selected-count';
  function updateCount(){
    var sel = grid.querySelectorAll('.selected').length;
    countEl.textContent = sel + ' product(s) selected';
  }
  checkboxes.forEach(function(cb){
    var img = cb.getAttribute('data-img') || '';
    var label = cb.closest('label') || cb.parentElement;
    var pname = label ? label.textContent.trim() : '';
    var ptype = cb.getAttribute('data-type') || '';
    var pprice = cb.getAttribute('data-price') || '';
    var card = document.createElement('div');
    card.className = 'product-thumb-item' + (cb.checked ? ' selected' : '');
    if(img){
      card.innerHTML = '<img src="'+img+'" alt="'+pname+'" loading="lazy"><div class="info"><div class="pname">'+pname+'</div><div class="pmeta">'+ptype+' &middot; '+pprice+'</div></div>';
    } else {
      card.innerHTML = '<div class="no-img">&#128247;</div><div class="info"><div class="pname">'+pname+'</div><div class="pmeta">'+ptype+' &middot; '+pprice+'</div></div>';
    }
    card.appendChild(cb);
    card.addEventListener('click', function(e){
      e.preventDefault();
      cb.checked = !cb.checked;
      card.classList.toggle('selected', cb.checked);
      updateCount();
    });
    grid.appendChild(card);
  });
  wrap.innerHTML = '';
  wrap.appendChild(grid);
  wrap.appendChild(countEl);
  updateCount();
})();
</script>
"""
        return f'<div id="product-thumb-wrap">{output}</div>{style}{script}'


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

    linked_products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.filter(is_active=True).order_by("title"),
        required=False,
        label="Assign Store Products",
        help_text="Click a product card to select/deselect it. Selected cards are highlighted in red.",
        widget=ProductThumbnailWidget,
    )

    class Meta:
        model = Artwork
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        """Set artwork FK on selected products; clear it on deselected ones."""
        selected = set(self.cleaned_data.get("linked_products", []))
        selected_pks = {p.pk for p in selected}
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
            "description": "Click a product card to select it. Selected cards highlight red.",
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
