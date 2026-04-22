import json, os
from datetime import datetime
from typing import Optional
from pathlib import Path
from agent_core.llm_client import chat
from calcom.calcom_client import get_booking_link_for_prospect, get_available_slots

STATE_DIR = Path(__file__).parent.parent.parent / "data" / "conversation_state"
STATE_DIR.mkdir(exist_ok=True, parents=True)

SYSTEM = """You are a sales assistant for Tenacious Consulting and Outsourcing.
Services: managed talent outsourcing (3–12 engineers, 6–24 months, $240–720K ACV) and project consulting (AI/ML/data builds, $80–300K).
Rules:
- Answer factually from the context brief only
- Never commit to specific capacity without "I'll confirm with our delivery team"
- Never fabricate case studies or client names
- If prospect shows interest in a call, offer the booking link
- Keep replies under 80 words for SMS, 120 words for email
Tone: direct, honest, no jargon."""

def get_state(prospect_id):
    path = STATE_DIR / f"{prospect_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"prospect_id":prospect_id,"stage":"outreach_sent","messages":[],"opted_out":False,"created_at":datetime.utcnow().isoformat()}

def save_state(prospect_id, state):
    path = STATE_DIR / f"{prospect_id}.json"
    state["updated_at"] = datetime.utcnow().isoformat()
    path.write_text(json.dumps(state, indent=2, default=str))

def handle_reply(prospect_id, reply_text, channel, hiring_brief, icp_result_dict,
                 prospect_name="there", prospect_email="", trace_id=None):
    state = get_state(prospect_id)
    if reply_text.upper().strip() in ("STOP","UNSUBSCRIBE","UNSUB"):
        state["opted_out"] = True
        save_state(prospect_id, state)
        return {"response_text":"You've been unsubscribed. We won't contact you again.","action":"opted_out","booking_url":None}

    state["messages"].append({"role":"user","content":reply_text,"timestamp":datetime.utcnow().isoformat(),"channel":channel})
    history = [{"role":m["role"],"content":m["content"]} for m in state["messages"]]

    wants_booking = any(kw in reply_text.lower() for kw in ["book","schedule","call","meet","time","availability","calendar","30 min","happy to","interested"])
    booking_url = None
    extra = ""
    if wants_booking:
        slots = get_available_slots()
        if slots and not slots[0].get("error"):
            slot_times = "\n".join(s["start"] for s in slots[:3] if s.get("start"))
            booking_url = get_booking_link_for_prospect(prospect_name=prospect_name, prospect_email=prospect_email,
                context_note=f"ICP: {icp_result_dict.get('segment_name','')} | {_summary(hiring_brief,icp_result_dict)[:200]}")
            extra = f"\n\nAvailable slots:\n{slot_times}\nBooking link: {booking_url}"

    cb = hiring_brief.get("crunchbase") or {}
    am = hiring_brief.get("ai_maturity") or {}
    context = f"Company: {cb.get('name','?')} | Sector: {cb.get('industry','N/A')}\nICP: Segment {icp_result_dict.get('segment')} — {icp_result_dict.get('segment_name')} ({icp_result_dict.get('confidence_label')} confidence)\nAI maturity: {am.get('score',0)}/3{extra}"

    text, usage = chat(messages=history, system=SYSTEM+f"\n\nProspect context:\n{context}", temperature=0.3, max_tokens=200, trace_id=trace_id)
    state["messages"].append({"role":"assistant","content":text,"timestamp":datetime.utcnow().isoformat(),"channel":channel,"llm_usage":usage})
    state["stage"] = "booking_offered" if booking_url else ("engaged" if state["stage"] == "outreach_sent" else state["stage"])
    save_state(prospect_id, state)
    return {"response_text":text,"action":"booking_offered" if booking_url else "continued","booking_url":booking_url,"llm_usage":usage}

def _summary(hiring_brief, icp_result):
    cb = hiring_brief.get("crunchbase") or {}
    am = hiring_brief.get("ai_maturity") or {}
    return f"{cb.get('name','?')} | {icp_result.get('segment_name','?')} | AI: {am.get('score',0)}/3"
