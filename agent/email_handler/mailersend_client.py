"""
email_handler/mailersend_client.py
MailerSend email integration for Tenacious Conversion Engine.

Drop-in replacement for resend_client.py with identical interface.
MailerSend supports inbound email routing on free tier — enabling
reply webhook functionality without a verified sending domain.

Environment variables:
  MAILERSEND_API_KEY          — MailerSend API token
  MAILERSEND_FROM_EMAIL       — verified sender email
  MAILERSEND_WEBHOOK_SECRET   — webhook signing secret (optional)
  MAILERSEND_INBOUND_DOMAIN   — inbound routing domain (optional)
"""
import os
import hmac
import hashlib
import logging
import json
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MAILERSEND_API_KEY    = os.getenv("MAILERSEND_API_KEY", "")
FROM_EMAIL            = os.getenv("MAILERSEND_FROM_EMAIL", os.getenv("RESEND_FROM_EMAIL", "outreach@example.com"))
WEBHOOK_SECRET        = os.getenv("MAILERSEND_WEBHOOK_SECRET", "")
MAILERSEND_API_URL    = "https://api.mailersend.com/v1"

REPLY_EVENTS  = {"inbound.message", "activity.sent"}
BOUNCE_EVENTS = {"activity.hard_bounced", "activity.soft_bounced", "activity.spam_complaint"}
OPEN_EVENTS   = {"activity.opened", "activity.clicked"}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {MAILERSEND_API_KEY}",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }


def send_outreach_email(
    to_email: str,
    subject: str,
    body: str,
    prospect_id: str,
    tags: Optional[dict] = None,
) -> dict:
    """
    Send a cold outreach email via MailerSend.
    Returns a structured result dict — never raises, always returns error info.
    Matches resend_client.send_outreach_email() interface exactly.
    """
    payload = {
        "from": {"email": FROM_EMAIL, "name": "Tenacious Intelligence"},
        "to": [{"email": to_email}],
        "subject": subject,
        "text": body,
        "tags": [prospect_id, "tenacious-outreach"],
        "variables": [
            {
                "email": to_email,
                "substitutions": [
                    {"var": "prospect_id", "value": prospect_id},
                ]
            }
        ],
        # Store prospect_id in headers for reply tracking
        "headers": [
            {"name": "X-Prospect-ID", "value": prospect_id},
            {"name": "X-Campaign",    "value": "tenacious-outreach"},
        ],
    }

    # Add extra tags if provided
    if tags:
        for k, v in tags.items():
            payload["tags"].append(f"{k}:{v}")

    try:
        resp = requests.post(
            f"{MAILERSEND_API_URL}/email",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()

        # MailerSend returns message ID in X-Message-Id header
        message_id = resp.headers.get("X-Message-Id", "")
        logger.info(
            f"Email sent to {to_email} | message_id={message_id} | prospect_id={prospect_id}"
        )
        return {
            "message_id": message_id,
            "to": to_email,
            "subject": subject,
            "status": "sent",
            "error": None,
        }

    except requests.HTTPError as e:
        error_body = ""
        try:
            error_body = e.response.json()
        except Exception:
            error_body = e.response.text
        logger.error(f"MailerSend send failed for {to_email}: {e} | {error_body}")
        return {
            "message_id": None,
            "to": to_email,
            "subject": subject,
            "status": "failed",
            "error": str(error_body),
        }
    except Exception as e:
        logger.error(f"MailerSend send failed for {to_email}: {e}")
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
    Matches resend_client.send_followup_email() interface exactly.
    """
    reply_subject = subject if subject.startswith("Re:") else f"Re: {subject}"

    headers_list = [
        {"name": "X-Prospect-ID", "value": prospect_id},
        {"name": "X-Type",        "value": "followup"},
    ]
    if thread_id:
        headers_list.append({"name": "In-Reply-To",  "value": thread_id})
        headers_list.append({"name": "References",   "value": thread_id})

    payload = {
        "from":    {"email": FROM_EMAIL, "name": "Tenacious Intelligence"},
        "to":      [{"email": to_email}],
        "subject": reply_subject,
        "text":    body,
        "tags":    [prospect_id, "followup"],
        "headers": headers_list,
    }

    try:
        resp = requests.post(
            f"{MAILERSEND_API_URL}/email",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        message_id = resp.headers.get("X-Message-Id", "")
        logger.info(f"Follow-up sent to {to_email} | message_id={message_id}")
        return {"message_id": message_id, "to": to_email, "status": "sent", "error": None}

    except Exception as e:
        logger.error(f"MailerSend follow-up failed for {to_email}: {e}")
        return {"message_id": None, "to": to_email, "status": "failed", "error": str(e)}


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify MailerSend webhook signature.
    MailerSend signs webhooks with HMAC-SHA256.
    Returns True if secret is not configured (development mode).
    Matches resend_client.verify_webhook_signature() interface exactly.
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
    Parse a MailerSend webhook event into normalized structure.
    Matches resend_client.parse_webhook_event() interface exactly.

    MailerSend inbound webhook payload structure:
    {
        "type": "inbound.message",
        "data": {
            "from": {"email": "prospect@company.com", "name": "Alex"},
            "to": [{"email": "outreach@yourdomain.com"}],
            "subject": "Re: Quick fix for your recent restructure",
            "text": "Thanks for reaching out...",
            "html": "<p>Thanks for reaching out...</p>",
            "headers": {"X-Prospect-ID": "abc123"},
            "message_id": "msg_xyz"
        }
    }

    Returns:
        {
            "event_type": str,
            "is_reply": bool,
            "is_bounce": bool,
            "prospect_id": str,
            "reply_text": str,
            "from_email": str,
            "email_data": dict,
            "should_process": bool,
        }
    """
    event_type = payload.get("type", "")
    data       = payload.get("data", {})

    # Extract prospect_id from custom headers
    raw_headers = data.get("headers", {})
    if isinstance(raw_headers, dict):
        prospect_id = raw_headers.get("X-Prospect-ID", "")
    elif isinstance(raw_headers, list):
        hmap = {h.get("name", ""): h.get("value", "") for h in raw_headers}
        prospect_id = hmap.get("X-Prospect-ID", "")
    else:
        prospect_id = ""

    # Extract reply text
    reply_text = data.get("text", "") or data.get("html", "")
    # Truncate to 500 chars for LLM context
    reply_text = reply_text[:500] if reply_text else ""

    # Extract sender email
    from_data  = data.get("from", {})
    from_email = from_data.get("email", "") if isinstance(from_data, dict) else ""

    is_reply  = event_type in REPLY_EVENTS
    is_bounce = event_type in BOUNCE_EVENTS

    if is_bounce:
        logger.warning(
            f"MailerSend bounce event '{event_type}' for prospect_id={prospect_id}"
        )

    return {
        "event_type":     event_type,
        "is_reply":       is_reply,
        "is_bounce":      is_bounce,
        "prospect_id":    prospect_id,
        "reply_text":     reply_text,
        "from_email":     from_email,
        "email_data":     data,
        "tags":           {},
        "should_process": is_reply and bool(prospect_id),
    }