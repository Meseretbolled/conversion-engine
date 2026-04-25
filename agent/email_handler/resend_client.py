"""
email_handler/resend_client.py
Resend email integration for Tenacious Conversion Engine.

Handles:
- Outbound cold outreach emails
- Follow-up emails in existing threads
- Webhook signature verification
- Bounce and failed-delivery event handling
"""
import os
import hmac
import hashlib
import logging
from typing import Optional

import resend

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "outreach@example.com")
WEBHOOK_SECRET = os.getenv("RESEND_REPLY_WEBHOOK_SECRET", "")

# Webhook event types we handle
REPLY_EVENTS = {"email.replied", "email.received"}
BOUNCE_EVENTS = {"email.bounced", "email.failed", "email.delivery_delayed"}
OPEN_EVENTS = {"email.opened", "email.clicked"}


def send_outreach_email(
    to_email: str,
    subject: str,
    body: str,
    prospect_id: str,
    tags: Optional[dict] = None,
) -> dict:
    """
    Send a cold outreach email via Resend.
    Returns a structured result dict — never raises, always returns error info.
    """
    params = {
        "from": FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "text": body,
        "headers": {
            "X-Prospect-ID": prospect_id,
            "X-Campaign": "tenacious-outreach",
        },
        "tags": [
            {"name": "prospect_id", "value": prospect_id},
            *([{"name": k, "value": re.sub(r"[^a-zA-Z0-9_-]", "_", str(v))} for k, v in (tags or {}).items()]),
        ],
    }
    try:
        response = resend.Emails.send(params)
        message_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
        logger.info(f"Email sent to {to_email} | message_id={message_id} | prospect_id={prospect_id}")
        return {
            "message_id": message_id,
            "to": to_email,
            "subject": subject,
            "status": "sent",
            "error": None,
        }
    except Exception as e:
        logger.error(f"Resend send failed for {to_email}: {e}")
        return {
            "message_id": None,
            "to": to_email,
            "subject": subject,
            "status": "failed",
            "error": str(e),
        }


def send_followup_email(
    to_email: str,
    subject: str,
    body: str,
    prospect_id: str,
    thread_id: Optional[str] = None,
) -> dict:
    """
    Send a follow-up email in an existing thread.
    """
    reply_subject = subject if subject.startswith("Re:") else f"Re: {subject}"
    params = {
        "from": FROM_EMAIL,
        "to": [to_email],
        "subject": reply_subject,
        "text": body,
        "headers": {
            "X-Prospect-ID": prospect_id,
            **({"In-Reply-To": thread_id, "References": thread_id} if thread_id else {}),
        },
        "tags": [
            {"name": "prospect_id", "value": prospect_id},
            {"name": "type", "value": "followup"},
        ],
    }
    try:
        response = resend.Emails.send(params)
        message_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
        logger.info(f"Follow-up sent to {to_email} | message_id={message_id}")
        return {"message_id": message_id, "to": to_email, "status": "sent", "error": None}
    except Exception as e:
        logger.error(f"Resend follow-up failed for {to_email}: {e}")
        return {"message_id": None, "to": to_email, "status": "failed", "error": str(e)}


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Resend webhook signature using HMAC-SHA256.
    Returns True if secret is not configured (development mode).
    """
    if not WEBHOOK_SECRET:
        return True
    try:
        expected = hmac.new(
            WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature.strip())
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {e}")
        return False


def parse_webhook_event(payload: dict) -> dict:
    """
    Parse a Resend webhook event into a normalized structure.

    Returns:
        {
            "event_type": str,       # e.g. "email.received", "email.bounced"
            "is_reply": bool,        # True if prospect replied
            "is_bounce": bool,       # True if delivery failed
            "prospect_id": str,      # from email tags
            "email_data": dict,      # raw email data
            "should_process": bool,  # True if pipeline should act on this
        }
    """
    event_type = payload.get("type", "")
    email_data = payload.get("data", {})

    # Extract prospect_id from tags
    tags = {t["name"]: t["value"] for t in email_data.get("tags", [])}
    prospect_id = tags.get("prospect_id", "")

    is_reply = event_type in REPLY_EVENTS
    is_bounce = event_type in BOUNCE_EVENTS

    if is_bounce:
        logger.warning(
            f"Email delivery event '{event_type}' for prospect_id={prospect_id} | "
            f"to={email_data.get('to', '')}"
        )

    return {
        "event_type": event_type,
        "is_reply": is_reply,
        "is_bounce": is_bounce,
        "prospect_id": prospect_id,
        "email_data": email_data,
        "tags": tags,
        "should_process": is_reply and bool(prospect_id),
    }