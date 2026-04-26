"""
email_handler/resend_client.py
Resend email integration for Tenacious Conversion Engine.

Reply-to routing:
  Every outbound email sets Reply-To: <prospect_id>@chuairkoon.resend.app
  When prospect replies, Resend routes it to /webhooks/email/reply
  We extract prospect_id from the recipient address local-part
  This eliminates fragile subject-line matching entirely.

Environment variables:
  RESEND_API_KEY
  RESEND_FROM_EMAIL        — verified sender (onboarding@resend.dev for sandbox)
  RESEND_REPLY_DOMAIN      — inbound domain (chuairkoon.resend.app)
  RESEND_REPLY_WEBHOOK_SECRET — optional webhook signing secret
"""
import re
import os
import hmac
import hashlib
import logging
from typing import Optional

import resend

logger = logging.getLogger(__name__)

resend.api_key      = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL          = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
REPLY_DOMAIN        = os.getenv("RESEND_REPLY_DOMAIN", "chuairkoon.resend.app")
WEBHOOK_SECRET      = os.getenv("RESEND_REPLY_WEBHOOK_SECRET", "")

REPLY_EVENTS  = {"email.replied", "email.received"}
BOUNCE_EVENTS = {"email.bounced", "email.failed", "email.delivery_delayed"}
OPEN_EVENTS   = {"email.opened", "email.clicked"}


def _make_reply_to(prospect_id: str) -> str:
    """
    Build the Reply-To address for a prospect.
    Sanitize prospect_id so it is a valid email local-part.
    e.g. prospect_id="abc12345" -> "abc12345@chuairkoon.resend.app"
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(prospect_id))
    return f"{safe_id}@{REPLY_DOMAIN}"


def _extract_prospect_id_from_to(to_address: str) -> Optional[str]:
    """
    Extract prospect_id from an inbound To address.
    "abc12345@chuairkoon.resend.app" -> "abc12345"
    Returns None if the address doesn't match the reply domain.
    """
    if not to_address:
        return None
    local = to_address.split("@")[0].strip().lstrip("<")
    domain = to_address.split("@")[-1].strip().rstrip(">")
    if REPLY_DOMAIN and domain != REPLY_DOMAIN:
        return None
    if not local:
        return None
    return local


def send_outreach_email(
    to_email: str,
    subject: str,
    body: str,
    prospect_id: str,
    tags: Optional[dict] = None,
) -> dict:
    """
    Send a cold outreach email via Resend.
    Sets Reply-To: <prospect_id>@chuairkoon.resend.app for automatic reply routing.
    """
    reply_to = _make_reply_to(prospect_id)
    params = {
        "from": FROM_EMAIL,
        "to": [to_email],
        "reply_to": reply_to,
        "subject": subject,
        "text": body,
        "headers": {
            "X-Prospect-ID": prospect_id,
            "X-Campaign": "tenacious-outreach",
        },
        "tags": [
            {"name": "prospect_id", "value": prospect_id},
            *([{"name": k, "value": re.sub(r"[^a-zA-Z0-9_-]", "_", str(v))}
               for k, v in (tags or {}).items()]),
        ],
    }
    try:
        response = resend.Emails.send(params)
        message_id = (response.get("id") if isinstance(response, dict)
                      else getattr(response, "id", None))
        logger.info(
            f"Email sent to {to_email} | message_id={message_id} "
            f"| prospect_id={prospect_id} | reply_to={reply_to}"
        )
        return {
            "message_id": message_id,
            "to": to_email,
            "subject": subject,
            "reply_to": reply_to,
            "status": "sent",
            "error": None,
        }
    except Exception as e:
        logger.error(f"Resend send failed for {to_email}: {e}")
        return {
            "message_id": None,
            "to": to_email,
            "subject": subject,
            "reply_to": reply_to,
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
    Send a follow-up reply email, preserving thread headers.
    """
    reply_to = _make_reply_to(prospect_id)
    reply_subject = subject if subject.startswith("Re:") else f"Re: {subject}"
    headers = {
        "X-Prospect-ID": prospect_id,
        "Reply-To": reply_to,
    }
    if thread_id:
        headers["In-Reply-To"] = thread_id
        headers["References"] = thread_id

    params = {
        "from": FROM_EMAIL,
        "to": [to_email],
        "reply_to": reply_to,
        "subject": reply_subject,
        "text": body,
        "headers": headers,
        "tags": [
            {"name": "prospect_id", "value": prospect_id},
            {"name": "type", "value": "followup"},
        ],
    }
    try:
        response = resend.Emails.send(params)
        message_id = (response.get("id") if isinstance(response, dict)
                      else getattr(response, "id", None))
        logger.info(f"Follow-up sent to {to_email} | message_id={message_id}")
        return {"message_id": message_id, "to": to_email,
                "reply_to": reply_to, "status": "sent", "error": None}
    except Exception as e:
        logger.error(f"Resend follow-up failed for {to_email}: {e}")
        return {"message_id": None, "to": to_email,
                "reply_to": reply_to, "status": "failed", "error": str(e)}


def fetch_email_content(email_id: str) -> Optional[dict]:
    """
    Fetch full email content from Resend API.
    The inbound webhook only contains email_id — we need this to get the body.
    """
    try:
        response = resend.Emails.get(email_id)
        if isinstance(response, dict):
            return response
        return vars(response) if hasattr(response, "__dict__") else None
    except Exception as e:
        logger.error(f"Failed to fetch email {email_id} from Resend: {e}")
        return None


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
    Parse a Resend webhook event.

    For inbound emails (email.received):
      1. Extract email_id from payload
      2. Fetch full content via resend.Emails.get(email_id)
      3. Extract prospect_id from To address local-part

    Returns normalized dict with prospect_id extracted from Reply-To routing.
    """
    event_type = payload.get("type", "")
    data = payload.get("data", {})

    # --- Inbound email (email.received) ---
    if event_type in REPLY_EVENTS:
        # Webhook payload has email_id but not full body
        email_id = data.get("email_id") or data.get("id") or ""

        # Try to fetch full email content
        full_email = None
        if email_id:
            full_email = fetch_email_content(email_id)

        # Use full email if available, fall back to webhook data
        email_data = full_email or data

        # Extract To address — this is how we identify the prospect
        to_raw = email_data.get("to", "")
        if isinstance(to_raw, list):
            to_address = to_raw[0] if to_raw else ""
        else:
            to_address = str(to_raw)

        # Extract prospect_id from Reply-To routing address
        prospect_id = _extract_prospect_id_from_to(to_address)

        # Fallback: check X-Prospect-ID header
        if not prospect_id:
            raw_headers = email_data.get("headers", {})
            if isinstance(raw_headers, dict):
                prospect_id = raw_headers.get("X-Prospect-ID", "")
            elif isinstance(raw_headers, list):
                hmap = {h.get("name", ""): h.get("value", "") for h in raw_headers}
                prospect_id = hmap.get("X-Prospect-ID", "")

        # Fallback: check tags from original send
        if not prospect_id:
            for tag in email_data.get("tags", []):
                if isinstance(tag, dict) and tag.get("name") == "prospect_id":
                    prospect_id = tag.get("value", "")
                    break

        # Extract reply text
        reply_text = (email_data.get("text", "")
                      or email_data.get("html", "")
                      or data.get("text", ""))
        reply_text = str(reply_text)[:1000]  # Truncate for LLM

        # Threading headers for reply
        from_email = email_data.get("from", "")
        if isinstance(from_email, list):
            from_email = from_email[0] if from_email else ""

        thread_id = email_id or data.get("id", "")

        if not prospect_id:
            logger.warning(
                f"Inbound email with no prospect_id match | "
                f"to={to_address} | email_id={email_id} | "
                "logged for manual review"
            )

        return {
            "event_type": event_type,
            "is_reply": True,
            "is_bounce": False,
            "prospect_id": prospect_id,
            "reply_text": reply_text,
            "from_email": from_email,
            "to_address": to_address,
            "thread_id": thread_id,
            "email_id": email_id,
            "email_data": email_data,
            "tags": {},
            "should_process": bool(prospect_id),
        }

    # --- Bounce / delivery failure ---
    if event_type in BOUNCE_EVENTS:
        email_data = data
        tags = {t["name"]: t["value"] for t in email_data.get("tags", [])
                if isinstance(t, dict)}
        prospect_id = tags.get("prospect_id", "")
        logger.warning(
            f"Email delivery event '{event_type}' for prospect_id={prospect_id}"
        )
        return {
            "event_type": event_type,
            "is_reply": False,
            "is_bounce": True,
            "prospect_id": prospect_id,
            "reply_text": "",
            "from_email": "",
            "to_address": "",
            "thread_id": "",
            "email_id": data.get("email_id", ""),
            "email_data": email_data,
            "tags": tags,
            "should_process": False,
        }

    # --- Other events (open, click, etc.) ---
    email_data = data
    tags = {t["name"]: t["value"] for t in email_data.get("tags", [])
            if isinstance(t, dict)}
    return {
        "event_type": event_type,
        "is_reply": False,
        "is_bounce": False,
        "prospect_id": tags.get("prospect_id", ""),
        "reply_text": "",
        "from_email": "",
        "to_address": "",
        "thread_id": "",
        "email_id": data.get("email_id", ""),
        "email_data": email_data,
        "tags": tags,
        "should_process": False,
    }