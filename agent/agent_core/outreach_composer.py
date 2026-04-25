import os

import json
import pathlib
from agent_core.llm_client import chat
from agent_core.icp_classifier import ICPResult

# ── Load seed materials ───────────────────────────────────────────────────────
_SEED_DIR = pathlib.Path(__file__).parent.parent.parent / "seed"

def _load_seed(filename: str) -> str:
    path = _SEED_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""

STYLE_GUIDE    = _load_seed("style_guide.md")
CALCOM_BOOKING_URL = os.getenv("CALCOM_BOOKING_URL", "https://cal.com/meseret-bolled-pxprep/tenacious-discovery-call")
ICP_DEFINITION = _load_seed("icp_definition.md")
COLD_TEMPLATE  = _load_seed("email_sequences/cold.md")
PRICING_SHEET  = _load_seed("pricing_sheet.md")

# Fallback if seed not found
if not STYLE_GUIDE:
    STYLE_GUIDE = """
Tenacious tone: direct, confident, not pushy. Every claim references a verifiable public fact.
Never say exciting opportunity, leverage, synergies, world-class, top talent, rockstar, ninja.
Never start with I hope this email finds you well.
Keep under 120 words. Subject line under 60 characters.
One CTA: a specific 30-minute discovery call. Include this exact booking link: {CALCOM_BOOKING_URL}
Signature: [First Name] / Research Partner / Tenacious Intelligence Corporation / gettenacious.com
"""

# ── Segment-specific pitch instructions ───────────────────────────────────────
SEGMENT_PROMPTS = {
    1: (
        "Prospect just closed Series A or B. They are growing faster than in-house hiring supports. "
        "High AI maturity (2-3): pitch scale your AI team. "
        "Low AI maturity (0-1): pitch stand up your first AI function. "
        "Reference the funding date and amount if verified."
    ),
    2: (
        "Prospect had a recent layoff or restructure. They need engineering output while cutting cost. "
        "Tenacious replaces higher-cost roles with offshore-equivalent engineers at 40-60% lower cost. "
        "Reference the verified layoff count and date. Do NOT say cost savings of X percent without grounding."
    ),
    3: (
        "Prospect has a new CTO or VP Engineering appointed in the last 90 days. "
        "New engineering leaders reassess vendor mix in their first 6 months. This is a narrow window. "
        "Frame as a research finding — mention the appointment if verified, otherwise ask."
    ),
    4: (
        "Prospect shows AI maturity 2-3 and likely has a specific ML or AI capability gap. "
        "Tenacious offers project-based consulting: ML platform, agentic systems, data contracts. "
        "Reference the competitor gap finding. Frame as a question, not a condemnation."
    ),
    None: (
        "No strong ICP signal detected. Write a brief, non-intrusive exploratory email. "
        "Do not assert any specific pain point without verified signal. Ask rather than tell."
    ),
}


def _clean_marker(line: str, marker: str) -> str:
    clean = line.strip().lstrip("*").strip()
    if clean.upper().startswith(marker.upper()):
        return clean[len(marker):].strip().lstrip("*").strip()
    return ""

def _is_marker(line: str, marker: str) -> bool:
    clean = line.strip().lstrip("*").strip()
    return clean.upper().startswith(marker.upper())


def compose_outreach_email(
    icp_result: ICPResult,
    hiring_brief: dict,
    competitor_brief: dict,
    prospect_first_name: str = "there",
    prospect_title: str = "",
    agent_name: str = "Research Partner",
    trace_id: str = None,
) -> dict:
    cb = hiring_brief.get("crunchbase") or {}
    fs = hiring_brief.get("funding_signal") or {}
    ls = hiring_brief.get("layoff_signal")
    js = hiring_brief.get("job_signal") or {}
    am = hiring_brief.get("ai_maturity") or {}
    ai_score = am.get("score", 0)

    signal_ctx = []
    if fs.get("is_recent") and fs.get("confidence") == "high":
        signal_ctx.append(
            f"VERIFIED: Closed {fs.get('funding_type')} {fs.get('days_since_funding')} days ago."
        )
    elif fs.get("is_recent"):
        signal_ctx.append("UNVERIFIED funding signal — do not assert, ask instead.")

    if ls and ls.get("within_120_days"):
        signal_ctx.append(
            f"VERIFIED: Layoff of {ls.get('laid_off_count')} ({ls.get('percentage')}%) "
            f"on {ls.get('date')}."
        )

    total_roles = js.get("total_open_roles", 0)
    ai_roles = js.get("ai_roles", 0)
    if total_roles >= 5:
        signal_ctx.append(
            f"VERIFIED: {total_roles} open roles, {ai_roles} AI-adjacent."
        )
    elif total_roles > 0:
        signal_ctx.append(
            f"WEAK SIGNAL ({total_roles} open roles — do NOT assert aggressive hiring)."
        )

    leadership = hiring_brief.get("leadership_signal") or {}
    if leadership.get("detected") and leadership.get("within_90_days"):
        signal_ctx.append(
            f"VERIFIED: New {leadership.get('title')} appointed "
            f"{leadership.get('days_since_appointment')} days ago."
        )

    if ai_score > 0:
        signal_ctx.append(
            f"AI maturity: {ai_score}/3 ({am.get('confidence', 'low')} confidence). "
            f"{am.get('summary', '')}"
        )

    honesty = []
    if total_roles < 5:
        honesty.append("Do NOT say scaling aggressively — fewer than 5 open roles. Ask rather than assert.")
    if icp_result.confidence_label == "low":
        honesty.append("ICP confidence LOW — frame as question or observation, not assertion.")
    if am.get("confidence") == "low" and ai_score >= 2:
        honesty.append("AI maturity 2+ but LOW confidence — use soft language.")
    if not signal_ctx:
        honesty.append("No verified signals. Write minimal exploratory email. Do not invent pain points.")
    if not honesty:
        honesty.append("Signal confidence sufficient — assert verified facts directly.")

    seg = icp_result.segment
    seg_prompt = SEGMENT_PROMPTS.get(seg, SEGMENT_PROMPTS[None])

    gap_narrative = (competitor_brief or {}).get("narrative", "N/A")
    gap_confidence = (competitor_brief or {}).get("confidence", "low")
    gap_instruction = (
        f"Weave this finding in (confidence: {gap_confidence}): {gap_narrative}"
        if gap_confidence in ("medium", "high") and gap_narrative != "N/A"
        else "No high-confidence competitor gap — omit gap reference."
    )

    prompt = f"""You are writing a cold outreach email for Tenacious Intelligence Corporation.

SEGMENT INSTRUCTION:
{seg_prompt}

STYLE GUIDE:
{STYLE_GUIDE[:1500]}

BOOKING LINK (include this exact URL in the email CTA): {CALCOM_BOOKING_URL}

PROSPECT:
- Name: {prospect_first_name}{f' ({prospect_title})' if prospect_title else ''}
- Company: {cb.get('name', 'the company')} | Sector: {cb.get('industry', 'technology')}
- ICP Segment: {icp_result.segment_name} | Confidence: {icp_result.confidence_label}

VERIFIED SIGNALS (ONLY reference these):
{chr(10).join(signal_ctx) if signal_ctx else 'No strong verified signals available.'}

COMPETITOR GAP:
{gap_instruction}

HONESTY CONSTRAINTS:
{chr(10).join('- ' + h for h in honesty)}

SIGNATURE TO USE:
{agent_name}
Research Partner
Tenacious Intelligence Corporation
gettenacious.com

Output format (plain text, no markdown, no asterisks):
SUBJECT: <subject line under 60 characters>
BODY:
<email body under 120 words>"""

    text, usage = chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=400,
        trace_id=trace_id,
    )

    subject, body = "", text
    lines = text.strip().split("\n")
    for i, line in enumerate(lines):
        if _is_marker(line, "SUBJECT:"):
            subject = _clean_marker(line, "SUBJECT:")
            rest = lines[i + 1:]
            if rest and _is_marker(rest[0], "BODY:"):
                rest = rest[1:]
            body = "\n".join(rest).strip()
            break

    if not subject and lines:
        subject = lines[0].strip().lstrip("*").strip()
        body = "\n".join(lines[1:]).strip()

    subject = subject.replace("**", "").strip()
    body = body.replace("**BODY:**", "").replace("**SUBJECT:**", "").strip()

    return {
        "subject": subject,
        "body": body,
        "variant": icp_result.pitch_variant,
        "segment": seg,
        "ai_maturity_score": ai_score,
        "confidence": icp_result.confidence_label,
        "confidence_notes": honesty,
        "llm_usage": usage,
    }