"""
gallery/models.py

Artwork, ArtworkImage (process steps), and ArtworkTag models.
The gallery is the creative heart of DarkForge Art.

Table prefix: dfa_
"""
import os

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify


def table_name(base_name: str) -> str:
    prefix = os.getenv("DB_TABLE_PREFIX", "dfa_")
    return f"{prefix}{base_name}"


class ArtworkTag(models.Model):
    """Tag / genre for filtering artwork (e.g. skull, graffiti, cyberpunk)."""
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    class Meta:
        db_table = table_name("artwork_tags")
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Artwork(models.Model):
    """
    Core artwork record.

    Images are stored in GitHub. The final_url (full resolution) is NEVER
    exposed in templates before purchase. Only preview_url (watermarked
    low-res) is shown publicly.
    """

    class Style(models.TextChoices):
        NEON_GRAFFITI = "neon_graffiti", _("Neon Graffiti")
        DARK_SURREALISM = "dark_surrealism", _("Dark Surrealism")
        OCCULT = "occult", _("Occult & Mystic")
        GOTHIC = "gothic", _("Gothic")
        BLACK_RED_METAL = "black_red_metal", _("Black & Red Metal")
        CYBERPUNK = "cyberpunk", _("Cyberpunk")
        STREET_ART = "street_art", _("Street Art Mural")
        JAPANESE = "japanese", _("Japanese-Inspired")
        TATTOO_FLASH = "tattoo_flash", _("Tattoo Flash")
        CHROME = "chrome", _("Chrome")
        AFRICAN = "african", _("African-Inspired")
        VINTAGE = "vintage", _("Distressed Vintage")
        MINIMAL_BW = "minimal_bw", _("Minimal Black & White")
        ORIGINAL = "original", _("Original Pencil")
        OTHER = "other", _("Other")

    class ArtworkType(models.TextChoices):
        ORIGINAL = "original", _("Original Drawing")
        DIGITAL = "digital", _("Digital Artwork")
        LIMITED = "limited", _("Limited Edition")
        MERCH_DESIGN = "merch_design", _("Merchandise Design")

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    description = models.TextField(blank=True)
    story = models.TextField(
        blank=True,
        help_text=_("The artistic story/process behind this piece - shown on the product page"),
    )
    style = models.CharField(max_length=30, choices=Style.choices, default=Style.NEON_GRAFFITI)
    artwork_type = models.CharField(
        max_length=20,
        choices=ArtworkType.choices,
        default=ArtworkType.DIGITAL,
    )

    # ── Image URLs (GitHub stored_path format: github://owner/repo/branch/path) ─
    original_pencil_url = models.CharField(
        max_length=512,
        blank=True,
        help_text=_("GitHub stored_path for the original pencil sketch"),
    )
    colored_url = models.CharField(
        max_length=512,
        blank=True,
        help_text=_("GitHub stored_path for the AI-colored intermediate version"),
    )
    preview_url = models.CharField(
        max_length=512,
        blank=True,
        help_text=_("GitHub stored_path for the watermarked low-res preview (shown publicly)"),
    )
    final_url = models.CharField(
        max_length=512,
        blank=True,
        help_text=_(
            "GitHub stored_path for the full-resolution final artwork. "
            "NEVER exposed in templates - only sent via signed download URL after payment."
        ),
    )

    # ── Meta ──────────────────────────────────────────────────────────────────
    tags = models.ManyToManyField(ArtworkTag, blank=True, related_name="artworks")
    is_published = models.BooleanField(default=False, db_index=True)
    is_featured = models.BooleanField(default=False, help_text=_("Show on homepage"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = table_name("artworks")
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Artwork.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.get_style_display()})"

    def get_preview_public_url(self):
        """Return the public (raw GitHub) URL of the watermarked preview."""
        from services.github_storage import github_public_url
        return github_public_url(self.preview_url)

    def get_original_pencil_public_url(self):
        """Return the public URL of the original pencil scan."""
        from services.github_storage import github_public_url
        return github_public_url(self.original_pencil_url)

    def get_colored_public_url(self):
        """Return the public URL of the AI-colored intermediate."""
        from services.github_storage import github_public_url
        return github_public_url(self.colored_url)


class ArtworkImage(models.Model):
    """
    Process/step images shown on the artwork product page.
    These tell the story: Original → Colored → Final.
    """
    artwork = models.ForeignKey(
        Artwork,
        on_delete=models.CASCADE,
        related_name="process_images",
    )
    image_url = models.CharField(
        max_length=512,
        help_text=_("GitHub stored_path for this step image"),
    )
    step_label = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('e.g. "Original Sketch", "Graffiti Treatment", "Final Artwork"'),
    )
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = table_name("artwork_images")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.artwork.title} - {self.step_label or 'Step ' + str(self.order)}"

    def get_public_url(self):
        from services.github_storage import github_public_url
        return github_public_url(self.image_url)
