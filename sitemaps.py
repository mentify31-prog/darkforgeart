"""
Sitemap configuration for DarkForge Art.
Registered in config/urls.py alongside the standard sitemap view.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from gallery.models import Artwork
from store.models import Product


class GallerySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.9

    def items(self):
        return Artwork.objects.filter(is_published=True)

    def location(self, obj):
        return f"/gallery/{obj.slug}/"

    def lastmod(self, obj):
        return obj.updated_at


class ProductSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Product.objects.filter(is_active=True)

    def location(self, obj):
        return f"/shop/product/{obj.slug}/"

    def lastmod(self, obj):
        return obj.updated_at


class StaticViewSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return [
            "gallery:home",
            "gallery:gallery",
            "store:shop",
            "commissions:commission_request",
            "gallery:about",
            "accounts:contact",
        ]

    def location(self, item):
        return reverse(item)
