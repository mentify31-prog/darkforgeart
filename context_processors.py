"""
context_processors.py — Global template context

Injects site-wide variables into every template.
"""

from django.conf import settings


def site_context(request):
    """Add platform-level context available in all templates."""
    return {
        "PLATFORM_NAME": getattr(settings, "PLATFORM_NAME", "DarkForge Art"),
        "BASE_URL": getattr(settings, "BASE_URL", ""),
        "PAYSTACK_PUBLIC_KEY": getattr(settings, "PAYSTACK_PUBLIC_KEY", ""),
    }
