"""Django email backend that sends mail through Resend.com."""
from __future__ import annotations

from django.core.mail.backends.base import BaseEmailBackend

from services.email_service import send_email_notification


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent_count = 0
        for message in email_messages:
            html_body = None
            for content, mimetype in getattr(message, "alternatives", []):
                if mimetype == "text/html":
                    html_body = content
                    break

            recipients = message.to or []
            if not recipients:
                continue

            for recipient in recipients:
                if send_email_notification(
                    message.subject,
                    recipient,
                    message.body,
                    html_body=html_body,
                    from_email=message.from_email,
                ):
                    sent_count += 1

        return sent_count
