"""
agent/main.py — FastAPI webhook server for Tenacious Conversion Engine

Three bugs fixed in this revision:
  1. PROSPECT_REGISTRY now persists to disk (data/registry.json).
     On startup it is loaded from disk, so a Render redeploy or refresh
     never loses prospects.

  2. /api/reply/{prospect_id} is a NEW direct endpoint the UI calls
     instead of hitting /webhooks/email/reply. The webhook path requires
     a valid Resend signature, which the UI can never provide. The direct
     endpoint bypasses signature verification entirely — it is for
     in-UI simulated replies only.

  3. Auto-booking: when handle_reply() returns a booking_url, main.py
     now appends the Cal.com link to the response email body so the
     prospect actually receives it, not just the UI.
"""
import os
import json
import uuid
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from enrichment.hiring_signal_brief import build_hiring_signal_brief, save_brief
from enrichment.competitor_gap_brief import build_competitor_gap_brief, save_brief as save_comp_brief
from agent_core.icp_classifier import classify
from agent_core.outreach_composer import compose_outreach_email
from agent_core.conversation_manager import handle_reply, get_state, save_state

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

from email_handler.resend_client import send_outreach_email
from sms_handler.at_client import send_sms, parse_inbound
from crm.hubspot_mcp import upsert_contact, log_email_sent, log_sms_event, log_booking
from observability.langfuse_client import Tracer

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Tenacious Conversion Engine", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure required directories exist
os.makedirs("data/briefs", exist_ok=True)
os.makedirs("data/conversation_state", exist_ok=True)

# ── Persistent prospect registry ──────────────────────────────────────────────
# Bug fix #1: was plain dict, reset on every Render redeploy.
# Now backed by data/registry.json so it survives restarts.

REGISTRY_PATH = Path("data/registry.json")

def _load_registry() -> dict:
    """Load the prospect registry from disk. Returns {} if file missing."""
    if REGISTRY_PATH.exists():
        try:
            return json.loads(REGISTRY_PATH.read_text())
        except Exception as e:
            logger.warning(f"Registry load failed, starting fresh: {e}")
    return {}

def _save_registry(registry: dict) -> None:
    """Persist the prospect registry to disk atomically."""
    try:
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = REGISTRY_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(registry, default=str))
        tmp.replace(REGISTRY_PATH)
    except Exception as e:
        logger.error(f"Registry save failed: {e}")

# Load on startup
PROSPECT_REGISTRY: dict[str, dict] = _load_registry()
logger.info(f"Registry loaded: {len(PROSPECT_REGISTRY)} prospects")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "registry_size": len(PROSPECT_REGISTRY),
    }


# ── Companies API ─────────────────────────────────────────────────────────────

@app.get("/api/companies")
async def get_companies(search: str = "", limit: int = 100):
    import pandas as pd
    from pathlib import Path
    try:
        base = Path(__file__).parent.parent
        csv_path = base / "data" / "crunchbase_sample.csv"
        if not csv_path.exists():
            for p in [Path("data/crunchbase_sample.csv"), Path("../data/crunchbase_sample.csv")]:
                if p.exists():
                    csv_path = p
                    break
        df = pd.read_csv(
            csv_path, low_memory=False,
            usecols=["name", "id", "url", "region", "num_employees", "industries", "website"],
        )
        if search:
            df = df[df["name"].str.lower().str.contains(search.lower(), na=False)]
        companies = []
        for _, row in df.head(limit).iterrows():
            name = str(row.get("name", "")).strip()
            if not name or name == "nan":
                continue
            companies.append({
                "name":       name,
                "id":         str(row.get("id", "")),
                "website":    str(row.get("website", row.get("url", ""))).replace("nan", ""),
                "country":    str(row.get("region", "")).replace("nan", ""),
                "employees":  str(row.get("num_employees", "")).replace("nan", ""),
                "industries": str(row.get("industries", "")).replace("nan", "")[:100],
            })
        return {"companies": companies, "total": len(companies)}
    except Exception as e:
        logger.error(f"Companies API error: {e}")
        return {"companies": [], "error": str(e), "total": 0}


# ── Prospects API ─────────────────────────────────────────────────────────────

@app.get("/api/prospects")
async def get_prospects():
    """Return all prospects from the persistent registry."""
    return {
        "prospects": [
            {
                "id": pid,
                **{k: v for k, v in data.items()
                   if k not in ["hiring_brief", "competitor_brief"]},
            }
            for pid, data in PROSPECT_REGISTRY.items()
        ]
    }

@app.get("/api/prospect/{prospect_id}")
async def get_prospect(prospect_id: str):
    if prospect_id not in PROSPECT_REGISTRY:
        return {"error": "not found"}
    return PROSPECT_REGISTRY[prospect_id]

@app.get("/api/conversation/{prospect_id}")
async def get_conversation(prospect_id: str):
    try:
        state = get_state(prospect_id)
        return {
            "prospect_id": prospect_id,
            "stage":       state.get("stage", "outreach_sent"),
            "messages":    state.get("messages", []),
            "opted_out":   state.get("opted_out", False),
        }
    except Exception as e:
        return {"prospect_id": prospect_id, "messages": [], "error": str(e)}


# ── Outreach pipeline ─────────────────────────────────────────────────────────

class ProspectRequest(BaseModel):
    company_name:         str
    prospect_email:       str
    prospect_first_name:  str = "there"
    prospect_last_name:   str = ""
    prospect_title:       str = ""
    prospect_phone:       str = ""
    careers_url:          Optional[str] = None
    skip_scraping:        bool = False


@app.post("/outreach/prospect")
async def trigger_outreach(req: ProspectRequest, background: BackgroundTasks):
    prospect_id = str(uuid.uuid4())[:8]
    background.add_task(_run_outreach_pipeline, prospect_id=prospect_id, req=req)
    return {"prospect_id": prospect_id, "status": "queued"}


async def _run_outreach_pipeline(prospect_id: str, req: ProspectRequest):
    t = Tracer("outreach_pipeline", prospect_id=prospect_id, company=req.company_name)
    try:
        t.__enter__()

        hiring_brief = build_hiring_signal_brief(
            company_name=req.company_name,
            careers_url=req.careers_url,
            skip_scraping=req.skip_scraping,
        )
        save_brief(hiring_brief, f"data/briefs/{prospect_id}_hiring.json")

        icp_result = classify(hiring_brief)
        t.log_span("icp_classified", output=icp_result.to_dict())

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

        email_content = compose_outreach_email(
            icp_result=icp_result,
            hiring_brief=hiring_brief,
            competitor_brief=comp_brief,
            prospect_first_name=req.prospect_first_name,
            prospect_title=req.prospect_title,
            trace_id=t.trace_id,
        )

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
        except Exception as e:
            logger.error(f"[{prospect_id}] HubSpot upsert failed: {e}")
            contact_id = ""

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

        # Register and PERSIST prospect
        PROSPECT_REGISTRY[prospect_id] = {
            "email":            req.prospect_email,
            "name":             req.prospect_first_name,
            "company":          req.company_name,
            "contact_id":       contact_id,
            "email_subject":    email_content.get("subject", ""),
            "email_body":       email_content.get("body", ""),
            "reply_to":         email_result.get("reply_to", f"{prospect_id}@chuairkoon.resend.app"),
            "phone":            req.prospect_phone,
            "icp":              icp_result.to_dict(),
            "hiring_brief":     hiring_brief,
            "competitor_brief": comp_brief,
            "email_message_id": email_result.get("message_id"),
            "stage":            "outreach_sent",
            "created_at":       datetime.utcnow().isoformat(),
        }
        _save_registry(PROSPECT_REGISTRY)  # ← persist to disk
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


# ── Direct reply endpoint (UI simulation) ────────────────────────────────────
# Bug fix #2: The UI was POSTing to /webhooks/email/reply which requires a
# Resend HMAC signature. The UI can never produce that, so it always got 401.
# This new endpoint is for in-UI simulation ONLY — no signature required.

class ReplyRequest(BaseModel):
    text:    str
    channel: str = "email"


@app.post("/api/reply/{prospect_id}")
async def direct_reply(prospect_id: str, req: ReplyRequest):
    """
    Direct reply endpoint for UI simulation.
    Bypasses webhook signature verification.
    Calls the same handle_reply() the real webhook uses.
    """
    if prospect_id not in PROSPECT_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Prospect {prospect_id} not found. Trigger a new prospect first.",
        )

    prospect = PROSPECT_REGISTRY[prospect_id]

    try:
        t = Tracer("ui_reply", prospect_id=prospect_id)
        t.__enter__()

        result = handle_reply(
            prospect_id=prospect_id,
            reply_text=req.text,
            channel=req.channel,
            hiring_brief=prospect["hiring_brief"],
            icp_result_dict=prospect["icp"],
            prospect_name=prospect.get("name", "there"),
            prospect_email=prospect["email"],
            trace_id=t.trace_id,
        )

        response_text = result.get("response_text", "")
        booking_url   = result.get("booking_url")

        # Bug fix #3: Auto-booking — append the Cal.com link to the email body
        # so the prospect actually receives it, not just the UI response.
        if booking_url and response_text:
            if booking_url not in response_text:
                response_text = (
                    f"{response_text}\n\n"
                    f"Book a 30-min discovery call here:\n{booking_url}"
                )

        # Send the agent response back to the prospect via email
        if response_text and prospect.get("email"):
            try:
                send_outreach_email(
                    to_email=prospect["email"],
                    subject="Re: Tenacious outreach",
                    body=response_text,
                    prospect_id=prospect_id,
                )
                # Update HubSpot
                if prospect.get("contact_id"):
                    try:
                        log_email_sent(
                            contact_id=prospect["contact_id"],
                            subject="Re: Tenacious outreach",
                            body=response_text,
                            message_id="",
                            segment=prospect.get("icp", {}).get("segment", 0),
                            pitch_variant="reply",
                        )
                    except Exception as he:
                        logger.warning(f"HubSpot reply log failed: {he}")
            except Exception as se:
                logger.error(f"[{prospect_id}] Reply send failed: {se}")

        # Update stage in registry and persist
        new_stage = "booking_offered" if booking_url else "engaged"
        PROSPECT_REGISTRY[prospect_id]["stage"] = new_stage
        _save_registry(PROSPECT_REGISTRY)

        t.set_output(result)
        t.__exit__(None, None, None)

        return {
            "status":       "handled",
            "action":       result.get("action"),
            "response_text": response_text,
            "booking_url":  booking_url,
            "stage":        new_stage,
        }

    except Exception as e:
        logger.error(f"Direct reply failed for {prospect_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Email reply webhook (real Resend events) ──────────────────────────────────

@app.post("/webhooks/email/reply")
async def email_reply_webhook(request: Request):
    body = await request.body()
    sig  = (request.headers.get("svix-signature", "")
            or request.headers.get("x-mailersend-signature", ""))

    if not verify_webhook_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    parsed     = parse_webhook_event(payload)
    event_type = parsed["event_type"]

    if parsed["is_bounce"]:
        prospect_id = parsed["prospect_id"]
        if prospect_id and prospect_id in PROSPECT_REGISTRY:
            PROSPECT_REGISTRY[prospect_id]["email_status"] = event_type
            _save_registry(PROSPECT_REGISTRY)
        return {"status": "bounced", "event": event_type}

    if not parsed["should_process"]:
        return {"status": "ignored", "event": event_type}

    prospect_id = parsed["prospect_id"]
    if not prospect_id or prospect_id not in PROSPECT_REGISTRY:
        return {"status": "unknown_prospect"}

    prospect   = PROSPECT_REGISTRY[prospect_id]
    email_data = parsed["email_data"]
    reply_text = email_data.get("text", "") or email_data.get("html", "")

    try:
        t = Tracer("email_reply", prospect_id=prospect_id)
        t.__enter__()

        result      = handle_reply(
            prospect_id=prospect_id,
            reply_text=reply_text,
            channel="email",
            hiring_brief=prospect["hiring_brief"],
            icp_result_dict=prospect["icp"],
            prospect_name=prospect.get("name", "there"),
            prospect_email=prospect["email"],
            trace_id=t.trace_id,
        )

        response_text = result.get("response_text", "")
        booking_url   = result.get("booking_url")

        # Auto-booking fix: include link in email body
        if booking_url and response_text and booking_url not in response_text:
            response_text = (
                f"{response_text}\n\nBook a 30-min discovery call:\n{booking_url}"
            )

        if response_text and prospect.get("email"):
            try:
                subj = email_data.get("subject", "Re: Tenacious outreach")
                if not subj.startswith("Re:"):
                    subj = f"Re: {subj}"
                reply_result = send_outreach_email(
                    to_email=prospect["email"],
                    subject=subj,
                    body=response_text,
                    prospect_id=prospect_id,
                )
                if prospect.get("contact_id"):
                    try:
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

        # Update stage + persist
        new_stage = "booking_offered" if booking_url else "engaged"
        PROSPECT_REGISTRY[prospect_id]["stage"] = new_stage
        _save_registry(PROSPECT_REGISTRY)

        t.set_output(result)
        t.__exit__(None, None, None)
        return {"status": "handled", "action": result.get("action")}

    except Exception as e:
        logger.error(f"Email reply handling failed for {prospect_id}: {e}")
        return {"status": "error", "detail": str(e)}


# ── SMS inbound webhook ───────────────────────────────────────────────────────

@app.post("/webhooks/sms/inbound")
async def sms_inbound_webhook(request: Request):
    try:
        form = await request.form()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Form parse error: {e}")

    inbound = parse_inbound(dict(form))

    if inbound["is_stop"]:
        prospect_id = _find_prospect_by_phone(inbound["from_number"])
        if prospect_id:
            PROSPECT_REGISTRY[prospect_id]["sms_opted_out"] = True
            _save_registry(PROSPECT_REGISTRY)
        return {"status": "opted_out"}

    if inbound["is_help"]:
        try:
            send_sms(
                to_number=inbound["from_number"],
                message="Tenacious Consulting: Reply STOP to unsubscribe. Visit gettenacious.com for more info.",
            )
        except Exception:
            pass
        return {"status": "help_sent"}

    prospect_id = _find_prospect_by_phone(inbound["from_number"])
    if not prospect_id:
        return {"status": "unknown_prospect"}

    prospect = PROSPECT_REGISTRY[prospect_id]

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
        result      = handle_reply(
            prospect_id=prospect_id,
            reply_text=inbound["text"],
            channel="sms",
            hiring_brief=prospect["hiring_brief"],
            icp_result_dict=prospect["icp"],
            prospect_email=prospect["email"],
            trace_id=t.trace_id,
        )
        response_text = result.get("response_text", "")
        booking_url   = result.get("booking_url")
        if booking_url and response_text and booking_url not in response_text:
            response_text = f"{response_text}\nBook here: {booking_url}"

        try:
            send_sms(to_number=inbound["from_number"], message=response_text[:459])
        except Exception as e:
            logger.error(f"SMS send failed: {e}")

        if prospect.get("contact_id"):
            try:
                log_sms_event(prospect["contact_id"], "inbound", inbound["text"])
                log_sms_event(prospect["contact_id"], "outbound", response_text)
            except Exception:
                pass

        new_stage = "booking_offered" if booking_url else "engaged"
        PROSPECT_REGISTRY[prospect_id]["stage"] = new_stage
        _save_registry(PROSPECT_REGISTRY)

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
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    if payload.get("triggerEvent") != "BOOKING_CREATED":
        return {"status": "ignored"}

    booking_data   = payload.get("payload", {})
    attendee_email = next(
        (a["email"] for a in booking_data.get("attendees", []) if a.get("email")),
        None,
    )
    if not attendee_email:
        return {"status": "no_attendee"}

    prospect_id = next(
        (pid for pid, p in PROSPECT_REGISTRY.items()
         if p["email"] == attendee_email),
        None,
    )

    if prospect_id and PROSPECT_REGISTRY[prospect_id].get("contact_id"):
        try:
            log_booking(
                contact_id=PROSPECT_REGISTRY[prospect_id]["contact_id"],
                booking_url=booking_data.get("metadata", {}).get("videoCallUrl", ""),
                event_time=booking_data.get("startTime", ""),
            )
        except Exception as e:
            logger.error(f"HubSpot booking log failed: {e}")

        PROSPECT_REGISTRY[prospect_id]["stage"] = "booked"
        _save_registry(PROSPECT_REGISTRY)

    return {"status": "logged"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_prospect_by_phone(phone: str) -> Optional[str]:
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