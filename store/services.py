"""
store/services.py

Helper services for product management, including uploading custom product mockup images
to the GitHub storage repository with local media fallback.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from django.conf import settings
from django.core.files.storage import default_storage
from services.github_storage import get_github_service

logger = logging.getLogger("darkforge")


def upload_product_mockup_files(physical_product: Any, files_list: list) -> list[str]:
    """
    Upload a list of mockup image files to GitHub storage repository (with local media fallback).
    Appends the uploaded image URLs to physical_product.mockup_images and saves the instance.

    Returns:
        List of newly uploaded image public URLs.
    """
    if not files_list or not physical_product:
        return []

    uploaded_urls: list[str] = []
    product = getattr(physical_product, "product", None)
    slug = product.slug if (product and getattr(product, "slug", None)) else "product"

    # Initialize GitHub storage service if configured
    gh_service = None
    if getattr(settings, "GITHUB_TOKEN", None) and getattr(settings, "GITHUB_REPO", None):
        try:
            gh_service = get_github_service()
        except Exception as exc:
            logger.warning("Could not initialize GitHubStorageService: %s", exc)

    for f in files_list:
        if not f:
            continue

        url: str | None = None

        # 1. Try uploading to GitHub repository
        if gh_service:
            try:
                res = gh_service.upload_file(
                    file_obj=f,
                    subdir="mockups",
                    filename_prefix=slug,
                )
                if res and res.repo_path:
                    url = f"/cdn/assets/{res.repo_path.lstrip('/')}"
                elif res and res.public_url:
                    url = res.public_url
            except Exception as exc:
                logger.error("GitHub mockup upload error for %s: %s", f.name, exc)
                url = None

        # 2. Fallback to local storage if GitHub service failed or isn't configured
        if not url:
            ext = os.path.splitext(f.name)[1].lower() or ".jpg"
            filename = f"mockups/{uuid.uuid4().hex[:10]}_{slug}{ext}"
            saved_path = default_storage.save(filename, f)
            url = default_storage.url(saved_path)

        if url:
            uploaded_urls.append(url)

    if uploaded_urls:
        current_images = list(physical_product.mockup_images or [])
        for u in uploaded_urls:
            if u not in current_images:
                current_images.append(u)

        physical_product.mockup_images = current_images
        if not physical_product.mockup_image_url and current_images:
            physical_product.mockup_image_url = current_images[0]

        physical_product.save(update_fields=["mockup_images", "mockup_image_url"])

    return uploaded_urls
