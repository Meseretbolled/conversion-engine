"""
agent/main.py — FastAPI webhook server for Tenacious Conversion Engine
Endpoints:
  POST /webhooks/email/reply      — Resend reply webhook
  POST /webhooks/sms/inbound      — Africa's Talking inbound SMS
  POST /webhooks/calcom/booking   — Cal.com booking confirmation
  POST /outreach/prospect         — Trigger full outreach pipeline
  GET  /health                    — Health check
"""
import os, json, uuid
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
from email_handler.resend_client import send_outreach_email, verify_webhook_signature
from sms_handler.at_client import send_sms, parse_inbound
from crm.hubspot_mcp import upsert_contact, log_email_sent, log_sms_event, log_booking
from observability.langfuse_client import Tracer

app = FastAPI(title="Tenacious Conversion Engine", version="0.1.0")
os.makedirs("data/briefs", exist_ok=True)
os.makedirs("data/conversation_state", exist_ok=True)
PROSPECT_REGISTRY: dict[str, dict] = {}

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

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
    prospect_id = str(uuid.uuid4())[:8]
    background.add_task(_run_outreach_pipeline, prospect_id=prospect_id, req=req)
    return {"prospect_id": prospect_id, "status": "queued"}

async def _run_outreach_pipeline(prospect_id: str, req: ProspectRequest):
    with Tracer("outreach_pipeline", prospect_id=prospect_id, company=req.company_name) as t:
        try:
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

            email_result = send_outreach_email(
                to_email=req.prospect_email,
                subject=email_content["subject"],
                body=email_content["body"],
                prospect_id=prospect_id,
                tags={"segment": str(icp_result.segment or 0), "variant": email_content["variant"]},
            )

            if contact_id:
                log_email_sent(
                    contact_id=contact_id,
                    subject=email_content["subject"],
                    body=email_content["body"],
                    message_id=email_result.get("message_id", ""),
                    segment=icp_result.segment or 0,
                    pitch_variant=email_content["variant"],
                )

            PROSPECT_REGISTRY[prospect_id] = {
                "email": req.prospect_email,
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
            t.set_output({"error": str(e)})
            raise

@app.post("/webhooks/email/reply")
async def email_reply_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("svix-signature", "")
    if not verify_webhook_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    payload = json.loads(body)
    if payload.get("type") != "email.replied":
        return {"status": "ignored"}
    email_data = payload.get("data", {})
    tags = {t["name"]: t["value"] for t in email_data.get("tags", [])}
    prospect_id = tags.get("prospect_id", "")
    if not prospect_id or prospect_id not in PROSPECT_REGISTRY:
        return {"status": "unknown_prospect"}
    prospect = PROSPECT_REGISTRY[prospect_id]
    reply_text = email_data.get("text", "") or email_data.get("html", "")
    with Tracer("email_reply", prospect_id=prospect_id) as t:
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
            log_sms_event(prospect["contact_id"], "inbound", reply_text)
        t.set_output(result)
    return {"status": "handled", "action": result["action"]}

@app.post("/webhooks/sms/inbound")
async def sms_inbound_webhook(request: Request):
    form = await request.form()
    inbound = parse_inbound(dict(form))
    if inbound["is_stop"]:
        return {"status": "opted_out"}
    if inbound["is_help"]:
        send_sms(to_number=inbound["from_number"],
                 message="Tenacious Consulting: Reply STOP to unsubscribe.")
        return {"status": "help_sent"}
    prospect_id = _find_prospect_by_phone(inbound["from_number"])
    if not prospect_id:
        return {"status": "unknown_prospect"}
    prospect = PROSPECT_REGISTRY[prospect_id]
    try:
        tracer_ctx = Tracer("sms_reply", prospect_id=prospect_id)
        t = tracer_ctx.__enter__()
    except Exception:
        class _FakeTracer:
            trace_id = ""
            def set_output(self, x): pass
        t = _FakeTracer()
        tracer_ctx = None
    result = handle_reply(
        prospect_id=prospect_id,
        reply_text=inbound["text"],
        channel="sms",
        hiring_brief=prospect["hiring_brief"],
        icp_result_dict=prospect["icp"],
        prospect_email=prospect["email"],
        trace_id=t.trace_id,
    )
    send_sms(to_number=inbound["from_number"], message=result["response_text"][:459])
    if prospect.get("contact_id"):
        log_sms_event(prospect["contact_id"], "inbound", inbound["text"])
        log_sms_event(prospect["contact_id"], "outbound", result["response_text"])
    t.set_output(result)
    return {"status": "replied"}

@app.post("/webhooks/calcom/booking")
async def calcom_booking_webhook(request: Request):
    payload = await request.json()
    if payload.get("triggerEvent") != "BOOKING_CREATED":
        return {"status": "ignored"}
    booking_data = payload.get("payload", {})
    attendee_email = next(
        (a["email"] for a in booking_data.get("attendees", []) if a.get("email")), None
    )
    if not attendee_email:
        return {"status": "no_attendee"}
    prospect_id = next(
        (pid for pid, p in PROSPECT_REGISTRY.items() if p["email"] == attendee_email), None
    )
    if prospect_id and PROSPECT_REGISTRY[prospect_id].get("contact_id"):
        log_booking(
            contact_id=PROSPECT_REGISTRY[prospect_id]["contact_id"],
            booking_url=booking_data.get("metadata", {}).get("videoCallUrl", ""),
            event_time=booking_data.get("startTime", ""),
        )
    return {"status": "logged"}

def _find_prospect_by_phone(phone: str) -> Optional[str]:
    for pid, p in PROSPECT_REGISTRY.items():
        if p.get("phone") == phone:
            return pid
    return None

if __name__ == "__main__":
    import uvicorn
    os.makedirs("data/briefs", exist_ok=True)
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("APP_PORT", "8000")), reload=True)

# Patch: safe SMS handler
from fastapi import Response
