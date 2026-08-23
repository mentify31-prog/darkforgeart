"""
gallery/views.py

Public gallery views for DarkForge Art.
HomeView, GalleryView, ArtworkDetailView.

IMPORTANT: final_url is NEVER passed to templates. Only preview_url (watermarked) is shown.
"""
from django.shortcuts import render, get_object_or_404
from django.views.decorators.cache import cache_page

from .models import Artwork, ArtworkTag
from store.models import Product


@cache_page(300)
def home(request):
    """
    Homepage: featured artwork hero, latest works, product teasers.
    """
    featured_artworks = (
        Artwork.objects.filter(is_published=True, is_featured=True)
        .prefetch_related("process_images", "tags")
        .order_by("-created_at")[:6]
    )
    latest_artworks = (
        Artwork.objects.filter(is_published=True)
        .prefetch_related("tags")
        .order_by("-created_at")[:12]
    )
    # Enrich with public preview URLs (GitHub raw URLs)
    for artwork in list(featured_artworks) + list(latest_artworks):
        artwork.preview_public_url = artwork.get_preview_public_url()

    context = {
        "featured_artworks": featured_artworks,
        "latest_artworks": latest_artworks,
        "page_title": "DarkForge Art - Original Dark & Graffiti Art",
        "meta_description": (
            "Premium dark graffiti artwork, digital prints, apparel and custom commissions. "
            "Original hand-drawn designs transformed into collectible art."
        ),
    }
    return render(request, "gallery/home.html", context)


@cache_page(300)
def gallery(request):
    """
    Full artwork gallery with tag/style filtering.
    """
    artworks = Artwork.objects.filter(is_published=True).prefetch_related("tags")

    # Filter by tag
    tag_slug = request.GET.get("tag")
    selected_tag = None
    if tag_slug:
        selected_tag = get_object_or_404(ArtworkTag, slug=tag_slug)
        artworks = artworks.filter(tags=selected_tag)

    # Filter by style
    style = request.GET.get("style")
    if style:
        artworks = artworks.filter(style=style)

    # Search query parameter ?q=
    from django.db.models import Q
    search_query = request.GET.get("q", "").strip()
    if search_query:
        artworks = artworks.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(tags__name__icontains=search_query)
        ).distinct()

    artworks = artworks.order_by("-created_at")

    # Attach public preview URLs
    for artwork in artworks:
        artwork.preview_public_url = artwork.get_preview_public_url()

    tags = ArtworkTag.objects.all()
    styles = Artwork.Style.choices

    context = {
        "artworks": artworks,
        "tags": tags,
        "styles": styles,
        "selected_tag": selected_tag,
        "selected_style": style,
        "page_title": "Gallery - DarkForge Art",
        "meta_description": (
            "Browse original dark graffiti artwork, skull designs, cyberpunk art, "
            "and gothic illustrations by DarkForge Art."
        ),
    }
    return render(request, "gallery/gallery.html", context)


def artwork_detail(request, slug):
    """
    Individual artwork page showing the creative process story and available products.

    SECURITY: final_url is EXCLUDED from context. Only preview_url is passed.
    """
    artwork = get_object_or_404(
        Artwork.objects.prefetch_related("process_images", "tags", "products"),
        slug=slug,
        is_published=True,
    )

    # Enrich process images with public URLs
    process_images = []
    for img in artwork.process_images.all():
        process_images.append({
            "label": img.step_label,
            "caption": img.caption,
            "url": img.get_public_url(),
        })

    # Available products for this artwork (active only)
    products = artwork.products.filter(is_active=True).select_related(
        "digital_detail", "physical_detail", "limited_detail", "license_detail"
    )

    context = {
        "artwork": artwork,
        "preview_url": artwork.get_preview_public_url(),
        "original_pencil_url": artwork.get_original_pencil_public_url(),
        "colored_url": artwork.get_colored_public_url(),
        "process_images": process_images,
        "products": products,
        # NEVER pass artwork.final_url here
        "page_title": f"{artwork.title} - DarkForge Art",
        "meta_description": artwork.description[:160] if artwork.description else (
            f"Original dark art: {artwork.title}. "
            "Available as digital download, print, and merchandise."
        ),
        "og_image": artwork.get_preview_public_url(),
    }
    return render(request, "gallery/artwork_detail.html", context)


def about(request):
    """About the artist and DarkForge Art story."""
    context = {
        "page_title": "About the Artist - DarkForge Art",
        "meta_description": (
            "Learn about DarkForge Art - original hand-drawn dark and graffiti artwork, "
            "digital prints, POD apparel, and custom commissions."
        ),
    }
    return render(request, "gallery/about.html", context)
