"""
store/models.py

Product system for DarkForge Art.

Four product types:
1. DigitalProduct - downloadable file (PNG, PDF, etc.)
2. PhysicalProduct - POD via Printful or Printify
3. LimitedEdition - limited run (digital, print, or original)
4. LicenseProduct - commercial/exclusive artwork license

All use a shared base Product model via OneToOne relationships.

Table prefix: dfa_
"""
import os

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

from gallery.models import Artwork


def table_name(base_name: str) -> str:
    prefix = os.getenv("DB_TABLE_PREFIX", "dfa_")
    return f"{prefix}{base_name}"


class ProductType(models.TextChoices):
    DIGITAL = "digital", _("Digital Download")
    PHYSICAL = "physical", _("Physical Product")
    LIMITED = "limited", _("Limited Edition")
    LICENSE = "license", _("Commercial License")


class Product(models.Model):
    """
    Base product. All product-type-specific fields live in sub-tables
    linked via OneToOneField.
    """
    artwork = models.ForeignKey(
        Artwork,
        on_delete=models.PROTECT,
        related_name="products",
    )
    product_type = models.CharField(
        max_length=20,
        choices=ProductType.choices,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("Price in KES (Paystack charges in smallest unit × 100)"),
    )
    currency = models.CharField(max_length=3, default="KES")
    is_active = models.BooleanField(default=True, db_index=True)
    show_in_gallery = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("Show this physical product in the Gallery page featured products section."),
    )
    gallery_sort_order = models.PositiveSmallIntegerField(
        default=0,
        help_text=_("Lower numbers appear first in the Gallery page featured products section."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = table_name("products")
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        super().save(*args, **kwargs)

        # Auto-create or sync DigitalProduct detail from linked Artwork's final_url
        if self.product_type in (ProductType.DIGITAL, ProductType.LICENSE) and self.artwork and self.artwork.final_url:
            digital, created = DigitalProduct.objects.get_or_create(
                product=self,
                defaults={
                    "file_url": self.artwork.final_url,
                    "file_format": "PNG" if self.artwork.final_url.lower().endswith(".png") else "JPG",
                    "license_type": LicenseType.COMMERCIAL if self.product_type == ProductType.LICENSE else LicenseType.PERSONAL,
                    "includes_description": "High-Resolution Digital Artwork File",
                }
            )
            if not created and not digital.file_url:
                digital.file_url = self.artwork.final_url
                digital.save(update_fields=["file_url"])

    def __str__(self):
        return f"{self.title} ({self.get_product_type_display()})"

    @property
    def price_kobo(self) -> int:
        """Return price in Paystack's smallest unit (1 KES = 100 kobo)."""
        return int(self.price * 100)

    @property
    def price_usd(self) -> float:
        """Return converted price in USD based on USD_EXCHANGE_RATE setting."""
        from django.conf import settings
        rate = getattr(settings, "USD_EXCHANGE_RATE", 130.0) or 130.0
        return round(float(self.price) / rate, 2)

    @property
    def preview_url(self) -> str:
        """
        Return the display preview image URL for this product.
        For physical products, returns the physical product mockup image.
        For digital/limited products, returns the watermarked artwork preview URL.
        """
        if self.product_type == ProductType.PHYSICAL:
            phys = getattr(self, "physical_detail", None)
            if phys and phys.mockup_image_url:
                return phys.mockup_image_url
        if self.artwork:
            return self.artwork.get_preview_public_url()
        return ""

    def get_type_detail(self):
        """Return the type-specific sub-object, or None."""
        if self.product_type == ProductType.DIGITAL:
            return getattr(self, "digital_detail", None)
        if self.product_type == ProductType.PHYSICAL:
            return getattr(self, "physical_detail", None)
        if self.product_type == ProductType.LIMITED:
            return getattr(self, "limited_detail", None)
        if self.product_type == ProductType.LICENSE:
            return getattr(self, "license_detail", None)
        return None


class LicenseType(models.TextChoices):
    PERSONAL = "personal", _("Personal Use")
    COMMERCIAL = "commercial", _("Commercial Use")
    EXCLUSIVE = "exclusive", _("Exclusive License")


class DigitalProduct(models.Model):
    """
    Downloadable file product.
    The file_url (GitHub stored_path) is NEVER shown in templates.
    After payment, a signed download URL is generated.
    """
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="digital_detail",
    )
    file_url = models.CharField(
        max_length=512,
        help_text=_(
            "GitHub stored_path for the full-resolution download file. "
            "Never exposed directly - only served via signed download URL."
        ),
    )
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    file_format = models.CharField(
        max_length=20,
        default="PNG",
        help_text=_('e.g. "PNG", "PDF", "ZIP"'),
    )
    license_type = models.CharField(
        max_length=20,
        choices=LicenseType.choices,
        default=LicenseType.PERSONAL,
    )
    includes_description = models.TextField(
        blank=True,
        help_text=_("What the customer receives, shown on the product page"),
    )

    class Meta:
        db_table = table_name("digital_products")

    def __str__(self):
        return f"Digital: {self.product.title}"


class FulfillmentProvider(models.TextChoices):
    PRINTFUL = "printful", _("Printful")
    PRINTIFY = "printify", _("Printify")


class PhysicalProduct(models.Model):
    """Physical merchandise fulfilled by Printful or Printify."""
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="physical_detail",
    )
    fulfillment_provider = models.CharField(
        max_length=20,
        choices=FulfillmentProvider.choices,
        default=FulfillmentProvider.PRINTFUL,
    )
    printful_product_id = models.CharField(max_length=100, blank=True)
    printify_product_id = models.CharField(max_length=100, blank=True)
    mockup_image_url = models.URLField(
        max_length=500,
        blank=True,
        help_text=_("Default product mockup image from Printify/Printful"),
    )
    mockup_images = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of all mockup image URLs for different colors and views"),
    )
    weight_grams = models.PositiveIntegerField(
        default=0,
        help_text=_("Approximate weight for shipping estimates"),
    )

    class Meta:
        db_table = table_name("physical_products")

    def __str__(self):
        return f"Physical: {self.product.title} via {self.get_fulfillment_provider_display()}"


class ProductVariant(models.Model):
    """Size/color variant of a physical product."""
    physical_product = models.ForeignKey(
        PhysicalProduct,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    size = models.CharField(max_length=10, blank=True, help_text=_('e.g. "S", "M", "XL"'))
    color = models.CharField(max_length=50, blank=True)
    printful_variant_id = models.CharField(max_length=100, blank=True)
    printify_variant_id = models.CharField(max_length=100, blank=True)
    price_override = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Leave blank to use base product price"),
    )
    stock_available = models.BooleanField(default=True)

    class Meta:
        db_table = table_name("product_variants")
        ordering = ["size", "color"]

    def __str__(self):
        return f"{self.physical_product.product.title} - {self.size} / {self.color}"

    @property
    def effective_price(self):
        if self.price_override is not None:
            return self.price_override
        return self.physical_product.product.price

    @property
    def effective_price_usd(self) -> float:
        from django.conf import settings
        rate = getattr(settings, "USD_EXCHANGE_RATE", 130.0) or 130.0
        return round(float(self.effective_price) / rate, 2)


class LimitedEdition(models.Model):
    """
    Limited-run edition of an artwork.
    Once edition_sold reaches edition_size, no more can be purchased.
    """
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="limited_detail",
    )
    edition_size = models.PositiveSmallIntegerField(
        default=25,
        help_text=_("Maximum number of copies available"),
    )
    edition_sold = models.PositiveSmallIntegerField(
        default=0,
        help_text=_("Number sold so far - auto-incremented on purchase"),
    )
    includes_original_sketch = models.BooleanField(
        default=False,
        help_text=_("Physical original pencil sketch included"),
    )
    includes_print = models.BooleanField(
        default=True,
        help_text=_("Signed print included"),
    )
    includes_digital = models.BooleanField(
        default=True,
        help_text=_("Digital download included"),
    )
    certificate_text = models.TextField(
        blank=True,
        help_text=_("Certificate of authenticity text"),
    )

    class Meta:
        db_table = table_name("limited_editions")

    def __str__(self):
        return f"Limited Edition: {self.product.title} ({self.edition_sold}/{self.edition_size})"

    @property
    def is_sold_out(self) -> bool:
        return self.edition_sold >= self.edition_size

    @property
    def remaining(self) -> int:
        return max(0, self.edition_size - self.edition_sold)

    def edition_label(self, copy_number: int) -> str:
        """Format the edition label for a specific copy, e.g. '003/025'."""
        return f"{copy_number:03d}/{self.edition_size:03d}"


class LicenseProduct(models.Model):
    """Commercial or exclusive artwork license sold as a product."""
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="license_detail",
    )
    license_scope = models.CharField(
        max_length=20,
        choices=LicenseType.choices,
        default=LicenseType.COMMERCIAL,
    )
    usage_description = models.TextField(
        blank=True,
        help_text=_("What the licensee is permitted to do with this artwork"),
    )
    allowed_uses = models.TextField(
        blank=True,
        help_text=_("Bullet-point list of permitted uses"),
    )
    restrictions = models.TextField(
        blank=True,
        help_text=_("What the licensee may NOT do"),
    )
    is_exclusive = models.BooleanField(
        default=False,
        help_text=_("If true, no other licenses for this artwork will be sold after purchase"),
    )

    class Meta:
        db_table = table_name("license_products")

    def __str__(self):
        return f"License: {self.product.title} ({self.get_license_scope_display()})"
