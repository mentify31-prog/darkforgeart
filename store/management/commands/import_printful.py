"""
store/management/commands/import_printful.py

Import all active physical products, variants, prices, and mockup images from Printful store into Django DB.
Usage:
    python manage.py import_printful
"""

from __future__ import annotations

import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from store.models import Product, PhysicalProduct, ProductVariant, ProductType, FulfillmentProvider
from gallery.models import Artwork
from fulfillment.printful import PrintfulProvider

logger = logging.getLogger("darkforge")


class Command(BaseCommand):
    help = "Import physical products from Printful API into Django DB"

    def handle(self, *args, **options):
        provider = PrintfulProvider()
        if not provider.api_key:
            self.stderr.write(self.style.ERROR("PRINTFUL_API_KEY is not configured in settings/.env!"))
            return

        # Auto-resolve store_id if not explicitly provided
        if not provider.store_id:
            stores_res = provider._get("stores")
            if isinstance(stores_res, dict) and stores_res.get("code") == 200:
                s_list = stores_res.get("result", [])
                if s_list:
                    provider.store_id = str(s_list[0].get("id"))
                    provider.session.headers["X-PF-Store-Id"] = provider.store_id
                    self.stdout.write(self.style.SUCCESS(f"Auto-selected Printful Store ID: {provider.store_id}"))

        res = provider._get("sync/products")
        if not isinstance(res, dict) or res.get("code") != 200:
            err = res.get("error", {}).get("message", str(res)) if isinstance(res, dict) else str(res)
            self.stderr.write(self.style.ERROR(f"Failed to fetch Printful products: {err}"))
            return

        products_data = res.get("result", [])
        if not products_data:
            self.stdout.write(self.style.WARNING("No sync products found in your Printful store."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(products_data)} products in Printful store."))

        default_artwork = Artwork.objects.first()
        if not default_artwork:
            self.stderr.write(self.style.ERROR("No Artwork exists in database! Create at least one Artwork first."))
            return

        rate = getattr(settings, "USD_EXCHANGE_RATE", 130.0)

        for p_item in products_data:
            p_id = str(p_item.get("id"))
            p_name = p_item.get("name", "Printful Product")
            thumbnail = p_item.get("thumbnail_url", "")

            # Fetch detailed product info + variants
            detail_res = provider._get(f"sync/products/{p_id}")
            if not isinstance(detail_res, dict) or detail_res.get("code") != 200:
                self.stderr.write(self.style.WARNING(f"Could not fetch details for Printful product {p_id} ({p_name})"))
                continue

            detail_data = detail_res.get("result", {})
            sync_vars = detail_data.get("sync_variants", [])
            if not sync_vars:
                continue

            first_retail = float(sync_vars[0].get("retail_price", 30.0))
            base_price_kes = round(first_retail * rate, 2)

            all_mockups = []
            if thumbnail:
                all_mockups.append(thumbnail)

            for sv in sync_vars:
                for f in sv.get("files", []):
                    p_url = f.get("preview_url")
                    if p_url and p_url not in all_mockups:
                        all_mockups.append(p_url)

            default_mockup = all_mockups[0] if all_mockups else ""

            product, created = Product.objects.get_or_create(
                title=p_name,
                defaults={
                    "artwork": default_artwork,
                    "product_type": ProductType.PHYSICAL,
                    "description": f"High quality physical merchandise printed and fulfilled by Printful.\n\n{p_name}",
                    "price": base_price_kes,
                    "currency": "KES",
                    "is_active": True,
                }
            )
            if not created:
                product.product_type = ProductType.PHYSICAL
                product.price = base_price_kes
                product.is_active = True
                product.save(update_fields=["product_type", "price", "is_active"])

            phys, _ = PhysicalProduct.objects.get_or_create(
                product=product,
                defaults={
                    "fulfillment_provider": FulfillmentProvider.PRINTFUL,
                    "printful_product_id": p_id,
                }
            )
            phys.fulfillment_provider = FulfillmentProvider.PRINTFUL
            phys.printful_product_id = p_id
            phys.mockup_image_url = default_mockup
            phys.mockup_images = all_mockups
            phys.save()

            added_vars = 0
            for sv in sync_vars:
                pv_id = str(sv.get("variant_id") or sv.get("id"))
                v_name = sv.get("name", "")
                
                size = str(sv.get("size", ""))
                color = str(sv.get("color", ""))

                if not size or not color:
                    parts = v_name.split("-")
                    if len(parts) > 1:
                        spec = parts[-1].strip()
                        if "/" in spec:
                            c_part, s_part = spec.split("/", 1)
                            color = color or c_part.strip()
                            size = size or s_part.strip()
                        else:
                            color = color or spec

                variant_price_usd = float(sv.get("retail_price", first_retail))
                variant_price_kes = round(variant_price_usd * rate, 2)

                var_obj, _ = ProductVariant.objects.get_or_create(
                    physical_product=phys,
                    printful_variant_id=pv_id,
                    defaults={
                        "size": size[:20],
                        "color": color[:30],
                        "price_override": variant_price_kes,
                        "stock_available": True,
                    }
                )
                var_obj.size = size[:20]
                var_obj.color = color[:30]
                var_obj.price_override = variant_price_kes
                var_obj.stock_available = True
                var_obj.save()
                added_vars += 1

            self.stdout.write(self.style.SUCCESS(
                f"Synced Printful product '{p_name}' with {added_vars} active variants."
            ))

        self.stdout.write(self.style.SUCCESS("Printful sync complete!"))
