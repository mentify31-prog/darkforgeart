"""
services/watermark.py

Applies a style-aware watermark to artwork preview images using Pillow.
Used to protect full-resolution artwork before purchase while optimizing visibility
based on artwork style (e.g. dark metal vs neon graffiti).
"""
from __future__ import annotations

import io
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("darkforge")

# Style classification sets
DARK_STYLES = {"black_red_metal", "gothic", "chrome", "dark_surrealism", "occult", "minimal_bw"}
VIBRANT_STYLES = {"neon_graffiti", "street_art", "japanese", "tattoo_flash"}


def get_style_watermark_params(style: str) -> tuple[int, int, int]:
    """
    Return (opacity, step_x_padding, step_y_padding) based on artwork style.
    """
    style_code = (style or "").lower().strip()
    if style_code in DARK_STYLES:
        # Lower opacity + wider spacing for dark metallic artwork
        return (70, 150, 95)
    elif style_code in VIBRANT_STYLES:
        # Crisp higher opacity + tight spacing for vibrant neon/street art
        return (130, 100, 65)
    else:
        # Balanced medium opacity for general artwork
        return (90, 120, 80)


def apply_watermark(
    image_bytes: bytes,
    text: str = "DarkForge Art • Preview • Not For Resale",
    style: str = "",
    opacity: int | None = None,
    max_width: int = 1200,
    max_height: int = 1200,
    output_format: str = "JPEG",
    quality: int = 80,
) -> bytes:
    """
    Apply a dual-tone translucent tiled watermark dynamically adapted to the artwork style.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    except Exception as exc:
        logger.error("Failed to open image for watermarking: %s", exc)
        return image_bytes

    # Downscale to preview size (protects full-res original)
    img.thumbnail((max_width, max_height), Image.LANCZOS)

    # Dynamic style params
    auto_opacity, pad_x, pad_y = get_style_watermark_params(style)
    final_opacity = opacity if opacity is not None else auto_opacity

    # Create a transparent overlay for the watermark
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Load font with appropriate scale
    try:
        font = ImageFont.truetype("arial.ttf", size=max(20, img.width // 26))
    except (IOError, OSError):
        font = ImageFont.load_default()

    # Get text dimensions
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Tile the watermark diagonally
    step_x = text_w + pad_x
    step_y = text_h + pad_y
    for x in range(-text_w, img.width + text_w, step_x):
        for y in range(-text_h, img.height + text_h, step_y):
            # Subtle dark shadow (contrast for light areas)
            draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, min(90, final_opacity)))
            # Translucent white text (contrast for dark areas)
            draw.text((x, y), text, font=font, fill=(240, 240, 240, final_opacity))

    # Composite watermark onto the image
    watermarked = Image.alpha_composite(img, overlay)

    # Convert back to RGB for JPEG output
    if output_format.upper() == "JPEG":
        watermarked = watermarked.convert("RGB")

    # Save to bytes
    output = io.BytesIO()
    watermarked.save(output, format=output_format, quality=quality if output_format.upper() == "JPEG" else None)
    return output.getvalue()


def create_preview_from_upload(file_obj, slug: str = "", style: str = "") -> bytes:
    """
    Read an uploaded file, apply style-aware watermark, and return the preview bytes.
    """
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        raw = file_obj.read()
    except Exception as exc:
        logger.error("Failed to read file for watermark preview: %s", exc)
        return b""

    label = slug or "DarkForge Art"
    return apply_watermark(
        raw,
        text=f"DarkForge Art • Preview • {label}",
        style=style,
    )
