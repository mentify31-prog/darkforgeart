"""
services/email_service.py

Resend.com email delivery for DarkForge Art.
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger("darkforge")

RESEND_API_URL = "https://api.resend.com/emails"


import threading


def send_email_notification(
    subject: str,
    recipient: str,
    body: str,
    *,
    html_body: str | None = None,
    from_email: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """Send a transactional email through Resend asynchronously."""
    api_key = getattr(settings, "RESEND_API_KEY", "").strip()
    sender = (from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "")).strip()
    recipient = recipient.strip()

    if not api_key:
        logger.warning("RESEND_API_KEY is not configured; email to %s was not sent.", recipient)
        return False
    if not sender or not recipient:
        return False

    payload: dict = {
        "from": sender,
        "to": [recipient],
        "subject": subject,
        "text": body,
    }
    if html_body:
        payload["html"] = html_body
    if reply_to:
        payload["reply_to"] = reply_to

    def _worker():
        try:
            response = requests.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15,
            )
            if response.status_code not in (200, 201):
                logger.error("Resend rejected email to %s: %s %s", recipient, response.status_code, response.text)
        except requests.RequestException:
            logger.exception("Failed to reach Resend for %s", recipient)

    threading.Thread(target=_worker, daemon=True).start()
    return True

    return True


def send_template_email(
    subject: str,
    recipient: str,
    template_txt: str,
    template_html: str | None = None,
    context: dict | None = None,
    reply_to: str | None = None,
) -> bool:
    """Send an email rendered from Django templates."""
    ctx = context or {}
    platform = getattr(settings, "PLATFORM_NAME", "DarkForge Art")
    base_url = getattr(settings, "BASE_URL", "")
    ctx.setdefault("PLATFORM_NAME", platform)
    ctx.setdefault("BASE_URL", base_url)

    body = render_to_string(template_txt, ctx)
    html_body = render_to_string(template_html, ctx) if template_html else None
    return send_email_notification(subject, recipient, body, html_body=html_body, reply_to=reply_to)


# ─── Specific Email Functions ──────────────────────────────────────────────────

def send_welcome_email(user) -> bool:
    platform = getattr(settings, "PLATFORM_NAME", "DarkForge Art")
    return send_template_email(
        subject=f"Welcome to {platform}",
        recipient=user.email,
        template_txt="emails/welcome.txt",
        template_html="emails/welcome.html",
        context={"user": user, "platform": platform},
    )


def send_verification_email(user, verify_url: str) -> bool:
    platform = getattr(settings, "PLATFORM_NAME", "DarkForge Art")
    return send_template_email(
        subject=f"Verify your email — {platform}",
        recipient=user.email,
        template_txt="emails/verify_email.txt",
        template_html="emails/verify_email.html",
        context={"user": user, "verify_url": verify_url, "platform": platform},
    )


def send_order_confirmation_email(order) -> bool:
    platform = getattr(settings, "PLATFORM_NAME", "DarkForge Art")
    return send_template_email(
        subject=f"Order Confirmed — {order.order_number}",
        recipient=order.shipping_email,
        template_txt="emails/order_confirmation.txt",
        template_html="emails/order_confirmation.html",
        context={"order": order, "platform": platform},
    )


def send_digital_delivery_email(order, delivery) -> bool:
    platform = getattr(settings, "PLATFORM_NAME", "DarkForge Art")
    base_url = getattr(settings, "BASE_URL", "")
    download_url = f"{base_url}/orders/download/{delivery.download_token}/"
    return send_template_email(
        subject=f"Your download is ready — {platform}",
        recipient=order.shipping_email,
        template_txt="emails/digital_delivery.txt",
        template_html="emails/digital_delivery.html",
        context={
            "order": order,
            "delivery": delivery,
            "download_url": download_url,
            "platform": platform,
        },
    )


def send_commission_received_email(commission) -> bool:
    platform = getattr(settings, "PLATFORM_NAME", "DarkForge Art")
    return send_template_email(
        subject=f"Commission request received — {platform}",
        recipient=commission.client.email,
        template_txt="emails/commission_received.txt",
        template_html="emails/commission_received.html",
        context={"commission": commission, "platform": platform},
    )


def send_commission_quoted_email(commission) -> bool:
    platform = getattr(settings, "PLATFORM_NAME", "DarkForge Art")
    base_url = getattr(settings, "BASE_URL", "")
    commission_url = f"{base_url}/commissions/{commission.pk}/"
    return send_template_email(
        subject=f"Your commission has been quoted — {platform}",
        recipient=commission.client.email,
        template_txt="emails/commission_quoted.txt",
        template_html="emails/commission_quoted.html",
        context={
            "commission": commission,
            "commission_url": commission_url,
            "platform": platform,
        },
    )


def send_commission_preview_email(commission, revision) -> bool:
    platform = getattr(settings, "PLATFORM_NAME", "DarkForge Art")
    base_url = getattr(settings, "BASE_URL", "")
    commission_url = f"{base_url}/commissions/{commission.pk}/"
    return send_template_email(
        subject=f"Your commission preview is ready — {platform}",
        recipient=commission.client.email,
        template_txt="emails/commission_preview.txt",
        template_html="emails/commission_preview.html",
        context={
            "commission": commission,
            "revision": revision,
            "commission_url": commission_url,
            "platform": platform,
        },
    )


def send_commission_completed_email(commission) -> bool:
    platform = getattr(settings, "PLATFORM_NAME", "DarkForge Art")
    base_url = getattr(settings, "BASE_URL", "")
    commission_url = f"{base_url}/commissions/{commission.pk}/"
    return send_template_email(
        subject=f"Your commission is complete — {platform}",
        recipient=commission.client.email,
        template_txt="emails/commission_completed.txt",
        template_html="emails/commission_completed.html",
        context={
            "commission": commission,
            "commission_url": commission_url,
            "platform": platform,
        },
    )


def send_shipping_notification_email(order, fulfillment_order) -> bool:
    platform = getattr(settings, "PLATFORM_NAME", "DarkForge Art")
    return send_template_email(
        subject=f"Your order has shipped — {platform}",
        recipient=order.shipping_email,
        template_txt="emails/shipping_notification.txt",
        template_html="emails/shipping_notification.html",
        context={
            "order": order,
            "fulfillment_order": fulfillment_order,
            "platform": platform,
        },
    )
