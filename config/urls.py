"""
DarkForge Art - Root URL Configuration
"""

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

from sitemaps import GallerySitemap, ProductSitemap, StaticViewSitemap

SITEMAPS = {
    "gallery": GallerySitemap,
    "products": ProductSitemap,
    "static": StaticViewSitemap,
}

from services.cdn_views import assets_proxy, github_asset_proxy

urlpatterns = [
    # Django built-in admin (keep for superuser access)
    path("django-admin/", admin.site.urls),

    # GitHub Private Repo Asset Proxy (previews, sketches, etc.)
    path("cdn/assets/<path:filepath>", assets_proxy, name="assets_proxy"),
    path("cdn/github/<str:owner>/<str:repo>/<str:ref>/<path:filepath>", github_asset_proxy, name="github_asset_proxy"),

    # App URLs
    path("", include("gallery.urls", namespace="gallery")),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("shop/", include("store.urls", namespace="store")),
    path("orders/", include("orders.urls", namespace="orders")),
    path("commissions/", include("commissions.urls", namespace="commissions")),
    path("payments/", include("payments.urls", namespace="payments")),
    path("fulfillment/", include("fulfillment.urls", namespace="fulfillment")),

    # SEO
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="django.contrib.sitemaps.views.sitemap"),
    path("robots.txt", lambda request: HttpResponse(
        f"User-agent: *\n"
        f"Disallow: /django-admin/\n"
        f"Disallow: /accounts/admin-panel/\n"
        f"Disallow: /payments/webhook/\n"
        f"Disallow: /fulfillment/\n"
        f"Disallow: /orders/download/\n"
        f"Disallow: /accounts/verify-email/\n"
        f"Disallow: /accounts/password-reset/\n"
        f"Disallow: /cart/\n"
        f"Disallow: /checkout/\n\n"
        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}\n",
        content_type="text/plain",
    )),
]

# Serve static + media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Custom error handlers
handler404 = "accounts.views.custom_404"
handler500 = "accounts.views.custom_500"
handler403 = "accounts.views.custom_403"
handler400 = "accounts.views.custom_400"
