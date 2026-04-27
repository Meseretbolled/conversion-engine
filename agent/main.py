"""
agent/main.py — FastAPI webhook server for Tenacious Conversion Engine
Endpoints:
  POST /webhooks/email/reply      — Resend reply webhook (handles replies + bounces)
  POST /webhooks/sms/inbound      — Africa's Talking inbound SMS (warm-channel only)
  POST /webhooks/calcom/booking   — Cal.com booking confirmation
  POST /outreach/prospect         — Trigger full outreach pipeline
  GET  /health                    — Health check
"""
import os
import json
import uuid
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from enrichment.hiring_signal_brief import build_hiring_signal_brief, save_brief
from enrichment.competitor_gap_brief import build_competitor_gap_brief, save_brief as save_comp_brief
from agent_core.icp_classifier import classify
from agent_core.outreach_composer import compose_outreach_email
from agent_core.conversation_manager import handle_reply, get_state, save_state
# Use MailerSend for inbound if API key is set, Resend for outbound
import os as _os
if _os.getenv("MAILERSEND_API_KEY"):
    from email_handler.mailersend_client import (
        verify_webhook_signature,
        parse_webhook_event,
    )
else:
    from email_handler.resend_client import (
        verify_webhook_signature,
        parse_webhook_event,
    )
# Outbound always uses Resend
from email_handler.resend_client import send_outreach_email
from sms_handler.at_client import send_sms, parse_inbound
from crm.hubspot_mcp import upsert_contact, log_email_sent, log_sms_event, log_booking
from observability.langfuse_client import Tracer

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Tenacious Conversion Engine", version="0.1.0")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure required directories exist on startup
os.makedirs("data/briefs", exist_ok=True)
os.makedirs("data/conversation_state", exist_ok=True)

# In-memory prospect registry (reset on redeploy — acceptable for challenge week)
PROSPECT_REGISTRY: dict[str, dict] = {}


# ── Health check ─────────────────────────────────────────────────────────────


import csv as _csv

@app.get("/api/companies")
async def get_companies(search: str = "", limit: int = 100):
    """Return companies from Crunchbase CSV for the pipeline UI."""
    import pandas as pd
    from pathlib import Path
    try:
        # Find the CSV relative to this file
        base = Path(__file__).parent.parent
        csv_path = base / "data" / "crunchbase_sample.csv"
        if not csv_path.exists():
            # Try alternate paths
            for p in [Path("data/crunchbase_sample.csv"), Path("../data/crunchbase_sample.csv")]:
                if p.exists():
                    csv_path = p
                    break
        df = pd.read_csv(csv_path, low_memory=False, usecols=["name","id","url","region","num_employees","industries","website"] if True else None)
        if search:
            mask = df["name"].str.lower().str.contains(search.lower(), na=False)
            df = df[mask]
        companies = []
        for _, row in df.head(limit).iterrows():
            name = str(row.get("name", "")).strip()
            if not name or name == "nan":
                continue
            companies.append({
                "name": name,
                "id": str(row.get("id", "")),
                "website": str(row.get("website", row.get("url", ""))).replace("nan",""),
                "country": str(row.get("region", "")).replace("nan",""),
                "employees": str(row.get("num_employees", "")).replace("nan",""),
                "industries": str(row.get("industries", "")).replace("nan","")[:100],
            })
        return {"companies": companies, "total": len(companies)}
    except Exception as e:
        logger.error(f"Companies API error: {e}")
        return {"companies": [], "error": str(e), "total": 0}

@app.get("/api/prospects")
async def get_prospects():
    """Return all active prospects in the registry."""
    return {
        "prospects": [
            {"id": pid, **{k: v for k, v in data.items() if k not in ["hiring_brief", "competitor_brief"]}}
            for pid, data in PROSPECT_REGISTRY.items()
        ]
    }

@app.get("/api/prospect/{prospect_id}")
async def get_prospect(prospect_id: str):
    """Return full prospect data including briefs."""
    if prospect_id not in PROSPECT_REGISTRY:
        return {"error": "not found"}
    return PROSPECT_REGISTRY[prospect_id]

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ── Outreach pipeline ─────────────────────────────────────────────────────────

class ProspectRequest(BaseModel):
    company_name: str
    prospect_email: str
    prospect_first_name: str = "there"
    prospect_last_name: str = ""
    prospect_title: str = ""
    prospect_phone: str = ""
    careers_url: Optional[str] = None
    skip_scraping: bool = False


@app.post("/outreach/prospect")
async def trigger_outreach(req: ProspectRequest, background: BackgroundTasks):
    """Queue a full outreach pipeline run for a prospect."""
    prospect_id = str(uuid.uuid4())[:8]
    background.add_task(_run_outreach_pipeline, prospect_id=prospect_id, req=req)
    return {"prospect_id": prospect_id, "status": "queued"}


async def _run_outreach_pipeline(prospect_id: str, req: ProspectRequest):
    """
    Full outreach pipeline:
    1. Enrich prospect from public signals
    2. Classify ICP segment
    3. Build competitor gap brief
    4. Compose signal-grounded email
    5. Upsert HubSpot contact
    6. Send email via Resend
    7. Log to HubSpot
    """
    t = Tracer("outreach_pipeline", prospect_id=prospect_id, company=req.company_name)
    try:
        t.__enter__()

        # Step 1 — Signal enrichment
        hiring_brief = build_hiring_signal_brief(
            company_name=req.company_name,
            careers_url=req.careers_url,
            skip_scraping=req.skip_scraping,
        )
        save_brief(hiring_brief, f"data/briefs/{prospect_id}_hiring.json")

        # Step 2 — ICP classification
        icp_result = classify(hiring_brief)
        t.log_span("icp_classified", output=icp_result.to_dict())
        logger.info(f"[{prospect_id}] ICP: Segment {icp_result.segment} ({icp_result.confidence_label})")

        # Step 3 — Competitor gap brief
        cb = hiring_brief.get("crunchbase") or {}
        am = hiring_brief.get("ai_maturity") or {}
        comp_brief = build_competitor_gap_brief(
            company_name=req.company_name,
            sector=cb.get("industry", "technology"),
            prospect_ai_score=am.get("score", 0),
            prospect_ai_signals=am.get("signals", []),
            trace_id=t.trace_id,
        )
        save_comp_brief(comp_brief, f"data/briefs/{prospect_id}_competitor.json")

        # Step 4 — Email composition
        email_content = compose_outreach_email(
            icp_result=icp_result,
            hiring_brief=hiring_brief,
            competitor_brief=comp_brief,
            prospect_first_name=req.prospect_first_name,
            prospect_title=req.prospect_title,
            trace_id=t.trace_id,
        )

        # Step 5 — HubSpot contact upsert
        try:
            hs_result = upsert_contact(
                email=req.prospect_email,
                first_name=req.prospect_first_name,
                last_name=req.prospect_last_name,
                company=req.company_name,
                phone=req.prospect_phone,
                job_title=req.prospect_title,
                crunchbase_id=cb.get("crunchbase_id", ""),
                icp_segment=icp_result.segment or 0,
                ai_maturity_score=am.get("score", 0),
            )
            contact_id = hs_result.get("id", "")
            logger.info(f"[{prospect_id}] HubSpot contact: {contact_id} ({hs_result.get('action')})")
        except Exception as e:
            logger.error(f"[{prospect_id}] HubSpot upsert failed: {e}")
            contact_id = ""

        # Step 6 — Send email via Resend
        email_result = send_outreach_email(
            to_email=req.prospect_email,
            subject=email_content["subject"],
            body=email_content["body"],
            prospect_id=prospect_id,
            tags={
                "segment": str(icp_result.segment or 0),
                "variant": email_content["variant"],
            },
        )
        if email_result.get("error"):
            logger.error(f"[{prospect_id}] Email send failed: {email_result['error']}")

        # Step 7 — Log email to HubSpot
        if contact_id and email_result.get("message_id"):
            try:
                log_email_sent(
                    contact_id=contact_id,
                    subject=email_content["subject"],
                    body=email_content["body"],
                    message_id=email_result.get("message_id", ""),
                    segment=icp_result.segment or 0,
                    pitch_variant=email_content["variant"],
                )
            except Exception as e:
                logger.error(f"[{prospect_id}] HubSpot email log failed: {e}")

        # Register prospect for reply handling
        PROSPECT_REGISTRY[prospect_id] = {
            "email": req.prospect_email,
            "name": req.prospect_first_name,
            "company": req.company_name,
            "contact_id": contact_id,
            "phone": req.prospect_phone,
            "icp": icp_result.to_dict(),
            "hiring_brief": hiring_brief,
            "competitor_brief": comp_brief,
            "email_message_id": email_result.get("message_id"),
        }
        t.set_output({"status": "sent", "email_id": email_result.get("message_id")})

    except Exception as e:
        logger.error(f"[{prospect_id}] Pipeline failed: {e}")
        t.set_output({"error": str(e)})
        raise
    finally:
        try:
            t.__exit__(None, None, None)
        except Exception:
            pass


# ── Email reply webhook ───────────────────────────────────────────────────────

@app.post("/webhooks/email/reply")
async def email_reply_webhook(request: Request):
    """
    Handles Resend webhook events:
    - email.received / email.replied → route to conversation manager
    - email.bounced / email.failed   → log and mark prospect
    - other events                   → ignore
    """
    body = await request.body()
    sig = request.headers.get("svix-signature", "") or request.headers.get("x-mailersend-signature", "")

    # Validate webhook signature
    if not verify_webhook_signature(body, sig):
        logger.warning("Email webhook: invalid signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Validate payload is valid JSON
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error(f"Email webhook: malformed JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    # Parse and classify the event
    parsed = parse_webhook_event(payload)
    event_type = parsed["event_type"]

    # Handle bounce/failure events
    if parsed["is_bounce"]:
        logger.warning(
            f"Email delivery event '{event_type}' for prospect_id={parsed['prospect_id']}"
        )
        prospect_id = parsed["prospect_id"]
        if prospect_id and prospect_id in PROSPECT_REGISTRY:
            PROSPECT_REGISTRY[prospect_id]["email_status"] = event_type
        return {"status": "bounced", "event": event_type, "prospect_id": prospect_id}

    # Ignore non-reply events
    if not parsed["should_process"]:
        return {"status": "ignored", "event": event_type}

    # Process reply
    prospect_id = parsed["prospect_id"]
    if not prospect_id or prospect_id not in PROSPECT_REGISTRY:
        logger.warning(f"Email reply: unknown prospect_id={prospect_id}")
        return {"status": "unknown_prospect"}

    prospect = PROSPECT_REGISTRY[prospect_id]
    email_data = parsed["email_data"]
    reply_text = email_data.get("text", "") or email_data.get("html", "")

    try:
        t = Tracer("email_reply", prospect_id=prospect_id)
        t.__enter__()
        result = handle_reply(
            prospect_id=prospect_id,
            reply_text=reply_text,
            channel="email",
            hiring_brief=prospect["hiring_brief"],
            icp_result_dict=prospect["icp"],
            prospect_name=prospect.get("name", "there"),
            prospect_email=prospect["email"],
            trace_id=t.trace_id,
        )
        if prospect.get("contact_id"):
            try:
                log_sms_event(prospect["contact_id"], "inbound", reply_text)
            except Exception as e:
                logger.error(f"HubSpot log failed: {e}")
        # Send the agent response back as email
        response_text = result.get("response_text", "")
        if response_text and prospect.get("email"):
            try:
                from email_handler.resend_client import send_outreach_email
                subj = email_data.get("subject", "Re: Tenacious outreach")
                if not subj.startswith("Re:"):
                    subj = f"Re: {subj}"
                reply_result = send_outreach_email(
                    to_email=prospect["email"],
                    subject=subj,
                    body=response_text,
                    prospect_id=prospect_id,
                )
                logger.info(f"[{prospect_id}] Reply email sent: {reply_result.get('message_id')}")
                # Update HubSpot with reply
                if prospect.get("contact_id"):
                    try:
                        from crm.hubspot_mcp import log_email_sent
                        log_email_sent(
                            contact_id=prospect["contact_id"],
                            subject=subj,
                            body=response_text,
                            message_id=reply_result.get("message_id", ""),
                            segment=prospect.get("icp", {}).get("segment", 0),
                            pitch_variant="reply",
                        )
                    except Exception as he:
                        logger.warning(f"HubSpot reply log failed: {he}")
            except Exception as se:
                logger.error(f"[{prospect_id}] Reply send failed: {se}")

        t.set_output(result)
        t.__exit__(None, None, None)
        return {"status": "handled", "action": result.get("action"), "response_sent": bool(response_text)}
    except Exception as e:
        logger.error(f"Email reply handling failed for {prospect_id}: {e}")
        return {"status": "error", "detail": str(e)}


# ── SMS inbound webhook ───────────────────────────────────────────────────────

@app.post("/webhooks/sms/inbound")
async def sms_inbound_webhook(request: Request):
    """
    Handles inbound SMS from Africa's Talking.

    Warm-channel gating: SMS replies are only processed for prospects who are
    already registered in PROSPECT_REGISTRY (i.e., have received an outreach email).
    Cold inbound SMS from unknown numbers returns 'unknown_prospect' and is not processed.

    Handles:
    - STOP/UNSUBSCRIBE → opt out prospect
    - HELP/INFO → send help text
    - Known prospect reply → route to conversation manager
    - Unknown number → ignore gracefully
    """
    try:
        form = await request.form()
    except Exception as e:
        logger.error(f"SMS webhook: form parse error: {e}")
        raise HTTPException(status_code=400, detail=f"Form parse error: {e}")

    inbound = parse_inbound(dict(form))

    # Handle opt-out
    if inbound["is_stop"]:
        logger.info(f"SMS opt-out from {inbound['from_number']}")
        prospect_id = _find_prospect_by_phone(inbound["from_number"])
        if prospect_id:
            PROSPECT_REGISTRY[prospect_id]["sms_opted_out"] = True
        return {"status": "opted_out"}

    # Handle help request
    if inbound["is_help"]:
        try:
            send_sms(
                to_number=inbound["from_number"],
                message="Tenacious Consulting: Reply STOP to unsubscribe. Visit gettenacious.com for more info.",
            )
        except Exception as e:
            logger.error(f"SMS help send failed: {e}")
        return {"status": "help_sent"}

    # Warm-channel gate: only process known prospects
    # SMS is secondary channel — only used for prospects who replied to email first
    prospect_id = _find_prospect_by_phone(inbound["from_number"])
    if not prospect_id:
        logger.info(f"SMS from unknown number {inbound['from_number']} — ignoring (warm-channel gate)")
        return {"status": "unknown_prospect"}

    prospect = PROSPECT_REGISTRY[prospect_id]

    # Route to conversation manager
    try:
        t = Tracer("sms_reply", prospect_id=prospect_id)
        t.__enter__()
    except Exception:
        class _FakeTracer:
            trace_id = ""
            def set_output(self, x): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
        t = _FakeTracer()

    try:
        result = handle_reply(
            prospect_id=prospect_id,
            reply_text=inbound["text"],
            channel="sms",
            hiring_brief=prospect["hiring_brief"],
            icp_result_dict=prospect["icp"],
            prospect_email=prospect["email"],
            trace_id=t.trace_id,
        )

        # Send SMS reply
        try:
            send_sms(
                to_number=inbound["from_number"],
                message=result["response_text"][:459],
            )
        except Exception as e:
            logger.error(f"SMS send failed to {inbound['from_number']}: {e}")

        # Log to HubSpot
        if prospect.get("contact_id"):
            try:
                log_sms_event(prospect["contact_id"], "inbound", inbound["text"])
                log_sms_event(prospect["contact_id"], "outbound", result["response_text"])
            except Exception as e:
                logger.error(f"HubSpot SMS log failed: {e}")

        t.set_output(result)
        return {"status": "replied"}

    except Exception as e:
        logger.error(f"SMS reply handling failed for {prospect_id}: {e}")
        return {"status": "error", "detail": str(e)}
    finally:
        try:
            t.__exit__(None, None, None)
        except Exception:
            pass


# ── Cal.com booking webhook ───────────────────────────────────────────────────

@app.post("/webhooks/calcom/booking")
async def calcom_booking_webhook(request: Request):
    """
    Handles Cal.com BOOKING_CREATED events.
    Updates the HubSpot contact with booking details and lifecycle stage.
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Cal.com webhook: malformed payload: {e}")
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    if payload.get("triggerEvent") != "BOOKING_CREATED":
        return {"status": "ignored"}

    booking_data = payload.get("payload", {})
    attendee_email = next(
        (a["email"] for a in booking_data.get("attendees", []) if a.get("email")), None
    )
    if not attendee_email:
        return {"status": "no_attendee"}

    prospect_id = next(
        (pid for pid, p in PROSPECT_REGISTRY.items() if p["email"] == attendee_email),
        None,
    )

    if prospect_id and PROSPECT_REGISTRY[prospect_id].get("contact_id"):
        try:
            log_booking(
                contact_id=PROSPECT_REGISTRY[prospect_id]["contact_id"],
                booking_url=booking_data.get("metadata", {}).get("videoCallUrl", ""),
                event_time=booking_data.get("startTime", ""),
            )
            logger.info(f"Booking logged for prospect_id={prospect_id}")
        except Exception as e:
            logger.error(f"HubSpot booking log failed: {e}")

    return {"status": "logged"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_prospect_by_phone(phone: str) -> Optional[str]:
    """Find prospect_id by phone number in registry."""
    for pid, p in PROSPECT_REGISTRY.items():
        if p.get("phone") == phone:
            return pid
    return None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("APP_PORT", "8000")),
        reload=True,
    )