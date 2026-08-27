"""
store/management/commands/import_printful.py

Import all active physical products, variants, prices, and mockup images from Printful store into Django DB.
Usage:
    python manage.py import_printful
"""

from __future__ import annotations

import logging
import re
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from store.models import Product, PhysicalProduct, ProductVariant, ProductType, FulfillmentProvider
from gallery.models import Artwork
from fulfillment.printful import PrintfulProvider

logger = logging.getLogger("darkforge")

VARIANT_SIZE_MAX_LENGTH = 50
VARIANT_COLOR_MAX_LENGTH = 50


def _numeric_sort_key(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


class Command(BaseCommand):
    help = "Import physical products from Printful API into Django DB"

    def _get_or_create_variant(self, physical_product, printful_variant_id, defaults):
        """
        Reuse one variant even if older imports created duplicate Printful variant rows.
        Extra duplicates are disabled instead of deleted to avoid breaking past orders.
        """
        qs = (
            ProductVariant.objects.filter(
                physical_product=physical_product,
                printful_variant_id=printful_variant_id,
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
                        f"Disabled {len(duplicate_ids)} duplicate Printful variant row(s) "
                        f"for variant ID {printful_variant_id}."
                    )
                )
            return variant, False

        return ProductVariant.objects.create(
            physical_product=physical_product,
            printful_variant_id=printful_variant_id,
            **defaults,
        ), True

    def handle(self, *args, **options):
        provider = PrintfulProvider()
        if not provider.api_key:
            self.stderr.write(self.style.ERROR("PRINTFUL_API_KEY is not configured in settings/.env!"))
            return

        stores_to_check = []
        if provider.store_id:
            stores_to_check = [str(provider.store_id)]
        else:
            stores_res = provider._get("stores")
            if isinstance(stores_res, dict) and stores_res.get("code") == 200:
                s_list = stores_res.get("result", [])
                for s in s_list:
                    stores_to_check.append(str(s.get("id")))

        if not stores_to_check:
            stores_to_check = [""]

        products_data_with_store = []
        for s_id in stores_to_check:
            params = {"store_id": s_id} if s_id else {}
            res = provider._get("sync/products", params=params)
            if isinstance(res, dict) and res.get("code") == 200:
                items = res.get("result", [])
                for item in items:
                    products_data_with_store.append((s_id, item))

        if not products_data_with_store:
            self.stdout.write(self.style.WARNING("No sync products found across your Printful store(s)."))
            return

        products_data_with_store.sort(key=lambda item: _numeric_sort_key(item[1].get("id")))
        self.stdout.write(self.style.SUCCESS(f"Found {len(products_data_with_store)} products across Printful store(s)."))

        default_artwork = Artwork.objects.first()
        if not default_artwork:
            self.stderr.write(self.style.ERROR("No Artwork exists in database! Create at least one Artwork first."))
            return

        rate = getattr(settings, "USD_EXCHANGE_RATE", 130.0)

        for s_id, p_item in products_data_with_store:
            p_id = str(p_item.get("id"))
            p_name = p_item.get("name", "Printful Product")
            thumbnail = p_item.get("thumbnail_url", "")

            # Fetch detailed product info + variants
            params = {"store_id": s_id} if s_id else {}
            detail_res = provider._get(f"sync/products/{p_id}", params=params)
            if not isinstance(detail_res, dict) or detail_res.get("code") != 200:
                self.stderr.write(self.style.WARNING(f"Could not fetch details for Printful product {p_id} ({p_name})"))
                continue

            detail_data = detail_res.get("result", {})
            sync_vars = detail_data.get("sync_variants", [])
            if not sync_vars:
                continue

            SHIPPING_BUFFER_USD = 13.00
            first_retail = float(sync_vars[0].get("retail_price", 30.0)) + SHIPPING_BUFFER_USD
            base_price_kes = round(first_retail * rate, 2)

            # ---------------------------------------------------------------
            # MOCKUP IMAGES (Automated Mockup Generator)
            # 1) Start with thumbnail from sync_product
            # 2) Call Printful Mockup Generator API to render ALL mockup views
            #    (Front, Back, Bottom, Side, Lifestyle, etc.)
            # 3) Fallback to sync variant preview files if generator fails
            # NEVER expose raw print files / artwork files.
            # ---------------------------------------------------------------
            all_mockups = []
            if thumbnail:
                all_mockups.append(thumbnail)

            # Build files payload with proper position bounding boxes
            files_payload = []
            seen_placements = set()
            for sv in sync_vars:
                for f in sv.get("files", []):
                    ftype = f.get("type")
                    if ftype and ftype != "preview":
                        placement = ftype
                        if placement == "default":
                            placement = "front"
                        if placement in seen_placements:
                            continue
                        seen_placements.add(placement)

                        url = f.get("preview_url") or f.get("url")
                        w = f.get("width") or 2100
                        h = f.get("height") or 2850
                        if url:
                            files_payload.append({
                                "placement": placement,
                                "image_url": url,
                                "position": {
                                    "area_width": w,
                                    "area_height": h,
                                    "width": w,
                                    "height": h,
                                    "top": 0,
                                    "left": 0,
                                }
                            })

            catalog_product_id = None
            catalog_variant_id = None
            if sync_vars:
                prod_info = sync_vars[0].get("product", {})
                catalog_product_id = prod_info.get("product_id")
                catalog_variant_id = prod_info.get("variant_id")

            if catalog_product_id and catalog_variant_id and files_payload:
                try:
                    import time
                    payload = {
                        "variant_ids": [catalog_variant_id],
                        "format": "jpg",
                        "files": files_payload,
                    }
                    path = f"mockup-generator/create-task/{catalog_product_id}?store_id={s_id}"
                    sc, task_res = provider._post(path, payload)
                    if sc in (200, 201):
                        task_key = task_res.get("result", {}).get("task_key")
                        if task_key:
                            for _attempt in range(12):
                                time.sleep(2)
                                poll = provider._get("mockup-generator/task", params={"task_key": task_key, "store_id": s_id})
                                poll_res = poll.get("result", {}) if isinstance(poll, dict) else {}
                                status = poll_res.get("status")
                                if status == "completed":
                                    for m in poll_res.get("mockups", []):
                                        m_url = m.get("mockup_url")
                                        if m_url and m_url not in all_mockups:
                                            all_mockups.append(m_url)
                                        for em in m.get("extra_mockups", []):
                                            em_url = em.get("mockup_url")
                                            if em_url and em_url not in all_mockups:
                                                all_mockups.append(em_url)
                                    break
                                elif status == "failed":
                                    break
                except Exception as exc:
                    self.stderr.write(self.style.WARNING(f"Mockup generator failed for {p_name}: {exc}"))

            # Fallback to variant preview files if generator failed
            if len(all_mockups) <= 1:
                for sv in sync_vars:
                    for f in sv.get("files", []):
                        if f.get("type") in ("preview", "mockup"):
                            p_url = f.get("preview_url") or f.get("url")
                            if p_url and p_url not in all_mockups:
                                all_mockups.append(p_url)

            default_mockup = all_mockups[0] if all_mockups else ""

            product, created = Product.objects.get_or_create(
                title=p_name,
                defaults={
                    "artwork": None,
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
            # Preserve any custom uploaded mockup URLs (e.g. /cdn/assets/, /media/, GitHub URLs)
            existing_custom_mockups = [
                url for url in (phys.mockup_images or [])
                if url and (url.startswith("/cdn/assets/") or url.startswith("/media/") or "github" in url)
            ]

            combined_mockups = list(all_mockups)
            for custom_url in existing_custom_mockups:
                if custom_url not in combined_mockups:
                    combined_mockups.append(custom_url)

            phys.mockup_image_url = default_mockup or (combined_mockups[0] if combined_mockups else "")
            phys.mockup_images = combined_mockups
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

                variant_price_usd = float(sv.get("retail_price", first_retail)) + SHIPPING_BUFFER_USD
                variant_price_kes = round(variant_price_usd * rate, 2)
                size = size[:VARIANT_SIZE_MAX_LENGTH]
                color = color[:VARIANT_COLOR_MAX_LENGTH]

                var_obj, _ = self._get_or_create_variant(
                    physical_product=phys,
                    printful_variant_id=pv_id,
                    defaults={
                        "size": size,
                        "color": color,
                        "price_override": variant_price_kes,
                        "stock_available": True,
                    },
                )
                var_obj.size = size
                var_obj.color = color
                var_obj.price_override = variant_price_kes
                var_obj.stock_available = True
                var_obj.save()
                added_vars += 1

            self.stdout.write(self.style.SUCCESS(
                f"Synced Printful product '{p_name}' with {added_vars} active variants."
            ))

        cache.clear()
        self.stdout.write(self.style.SUCCESS("Printful sync complete!"))
