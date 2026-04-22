import os, hmac, hashlib
import resend
from typing import Optional

resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "outreach@example.com")
WEBHOOK_SECRET = os.getenv("RESEND_REPLY_WEBHOOK_SECRET", "")

def send_outreach_email(to_email, subject, body, prospect_id, tags=None):
    params = {
        "from": FROM_EMAIL, "to": [to_email], "subject": subject, "text": body,
        "headers": {"X-Prospect-ID": prospect_id, "X-Campaign": "tenacious-outreach"},
        "tags": [{"name":"prospect_id","value":prospect_id},
                 *([{"name":k,"value":str(v)} for k,v in (tags or {}).items()])],
    }
    response = resend.Emails.send(params)
    return {"message_id": response.get("id"), "to": to_email, "subject": subject, "status": "sent"}

def send_followup_email(to_email, subject, body, prospect_id, thread_id=None):
    params = {
        "from": FROM_EMAIL, "to": [to_email],
        "subject": subject if subject.startswith("Re:") else f"Re: {subject}",
        "text": body,
        "headers": {"X-Prospect-ID": prospect_id,
                    **({"In-Reply-To":thread_id,"References":thread_id} if thread_id else {})},
        "tags": [{"name":"prospect_id","value":prospect_id},{"name":"type","value":"followup"}],
    }
    response = resend.Emails.send(params)
    return {"message_id": response.get("id"), "to": to_email, "status": "sent"}

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        return True
    expected = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
