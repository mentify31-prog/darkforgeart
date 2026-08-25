"""
store/management/commands/import_printify.py

Management command to automatically sync products and variants from Printify.
Usage:
    python manage.py import_printify
"""
import re
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db.models import Count

from gallery.models import Artwork
from store.models import Product, ProductType, PhysicalProduct, ProductVariant, FulfillmentProvider
from fulfillment.printify import PrintifyProvider


class Command(BaseCommand):
    help = "Automatically sync and import all products and variants from Printify API."

    def _get_or_create_variant(self, physical_product, printify_variant_id, defaults):
        """
        Reuse one variant even if older imports created duplicate Printify variant rows.
        Extra duplicates are disabled instead of deleted to avoid breaking past orders.
        """
        qs = (
            ProductVariant.objects.filter(
                physical_product=physical_product,
                printify_variant_id=printify_variant_id,
            )
            .annotate(order_count=Count("order_items"))
            .order_by("-order_count", "pk")
        )
        variant = qs.first()
        if variant:
            duplicate_ids = list(qs.values_list("pk", flat=True)[1:])
            if duplicate_ids:
                ProductVariant.objects.filter(pk__in=duplicate_ids).update(stock_available=False)
                self.stderr.write(
                    self.style.WARNING(
                        f"Disabled {len(duplicate_ids)} duplicate Printify variant row(s) "
                        f"for variant ID {printify_variant_id}."
                    )
                )
            return variant, False

        return ProductVariant.objects.create(
            physical_product=physical_product,
            printify_variant_id=printify_variant_id,
            **defaults,
        ), True

    def handle(self, *args, **options):
        p = PrintifyProvider()
        res = p._get(f"shops/{p.shop_id}/products.json")
        items = res.get("data", []) if isinstance(res, dict) else res
        rate = getattr(settings, "USD_EXCHANGE_RATE", 130.0) or 130.0

        self.stdout.write(self.style.SUCCESS(f"Connected to Printify Shop ID: {p.shop_id}"))
        self.stdout.write(f"Found {len(items)} products in Printify shop.")

        default_artwork = Artwork.objects.first()

        for item in items:
            p_id = item.get("id")
            title = item.get("title")
            full_desc = item.get("description", "").strip()
            images = item.get("images", [])
            all_mockup_urls = [img.get("src") for img in images if img.get("src")]

            enabled_vars = [v for v in item.get("variants", []) if v.get("is_enabled")]
            if not enabled_vars:
                continue

            SHIPPING_BUFFER_USD = 9.99
            base_cost_usd = (enabled_vars[0].get("price", 0) / 100.0) + SHIPPING_BUFFER_USD
            base_price_kes = round(base_cost_usd * rate, 2)

            product, created = Product.objects.get_or_create(
                title=title,
                defaults={
                    "artwork": default_artwork,
                    "product_type": ProductType.PHYSICAL,
                    "description": full_desc,
                    "price": base_price_kes,
                    "currency": "KES",
                    "is_active": True,
                }
            )
            if not created:
                product.product_type = ProductType.PHYSICAL
                product.description = full_desc
                product.price = base_price_kes
                product.is_active = True
                product.save(update_fields=["product_type", "description", "price", "is_active"])

            phys, _ = PhysicalProduct.objects.get_or_create(
                product=product,
                defaults={
                    "fulfillment_provider": FulfillmentProvider.PRINTIFY,
                    "printify_product_id": p_id,
                }
            )
            # Preserve any custom uploaded mockup URLs (e.g. /cdn/assets/, /media/, GitHub URLs)
            existing_custom_mockups = [
                url for url in (phys.mockup_images or [])
                if url and (url.startswith("/cdn/assets/") or url.startswith("/media/") or "github" in url)
            ]

            combined_mockups = list(all_mockup_urls)
            for custom_url in existing_custom_mockups:
                if custom_url not in combined_mockups:
                    combined_mockups.append(custom_url)

            phys.mockup_images = combined_mockups

            default_img = next((img for img in images if img.get("is_default")), None)
            if default_img and default_img.get("src"):
                phys.mockup_image_url = default_img["src"]
            elif combined_mockups:
                phys.mockup_image_url = combined_mockups[0]
            phys.save()

            added_vars = 0
            for v in enabled_vars:
                v_id = str(v.get("id"))
                v_title = v.get("title", "")
                v_cost_usd = (v.get("price", 0) / 100.0) + SHIPPING_BUFFER_USD
                v_price_kes = round(v_cost_usd * rate, 2)

                parts = v_title.split("/")
                color = parts[0].strip() if len(parts) > 0 else ""
                size = parts[1].strip() if len(parts) > 1 else v_title

                variant, _ = self._get_or_create_variant(
                    physical_product=phys,
                    printify_variant_id=v_id,
                    defaults={
                        "size": size,
                        "color": color,
                        "price_override": v_price_kes,
                        "stock_available": True,
                    },
                )
                variant.size = size
                variant.color = color
                variant.price_override = v_price_kes
                variant.stock_available = True
                variant.save()
                added_vars += 1

            self.stdout.write(self.style.SUCCESS(f"Synced '{title}' with {added_vars} active variants."))

        self.stdout.write(self.style.SUCCESS("Printify sync complete!"))
