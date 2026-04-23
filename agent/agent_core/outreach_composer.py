from agent_core.llm_client import chat
from agent_core.icp_classifier import ICPResult

STYLE_GUIDE = """
Tenacious tone: direct, confident, not pushy. Every claim references a verifiable public fact.
Never say "exciting opportunity", "leverage", "synergies", "world-class".
Never start with "I hope this email finds you well".
Keep under 120 words. One CTA: a specific 30-minute discovery call.
Sign off: [Name], Tenacious Consulting and Outsourcing
"""

SEGMENT_PROMPTS = {
    1: "Prospect just closed Series A or B. They are growing faster than in-house hiring supports.\nHigh AI maturity (2-3): pitch 'scale your AI team'. Low AI maturity (0-1): pitch 'stand up your first AI function'.",
    2: "Prospect had a recent layoff/restructure. They need engineering output while cutting cost. Tenacious replaces higher-cost roles with offshore equivalents.",
    3: "Prospect has a new CTO or VP Engineering (last 90 days). New leaders reassess vendor mix in their first 6 months. This is a narrow window.",
    4: "Prospect shows AI maturity 2-3 and likely has a specific ML/AI capability gap. Tenacious offers project-based consulting for ML platform, agentic systems, data contracts.",
    None: "No strong ICP signal. Write a brief, non-intrusive exploratory email without claiming specifics.",
}

def _clean_marker(line: str, marker: str) -> str:
    """Strip a marker like SUBJECT: or **SUBJECT:** from the start of a line."""
    clean = line.strip().lstrip("*").strip()
    if clean.upper().startswith(marker.upper()):
        return clean[len(marker):].strip().lstrip("*").strip()
    return ""

def _is_marker(line: str, marker: str) -> bool:
    """Check if a line starts with a marker, handling ** bold markdown."""
    clean = line.strip().lstrip("*").strip()
    return clean.upper().startswith(marker.upper())

def compose_outreach_email(icp_result: ICPResult, hiring_brief, competitor_brief,
                            prospect_first_name="there", prospect_title="", trace_id=None):
    cb = hiring_brief.get("crunchbase") or {}
    fs = hiring_brief.get("funding_signal") or {}
    ls = hiring_brief.get("layoff_signal")
    js = hiring_brief.get("job_signal") or {}
    am = hiring_brief.get("ai_maturity") or {}
    ai_score = am.get("score", 0)

    signal_ctx = []
    if fs.get("is_recent") and fs.get("confidence") == "high":
        signal_ctx.append(f"VERIFIED: Closed {fs.get('funding_type')} {fs.get('days_since_funding')} days ago.")
    elif fs.get("is_recent"):
        signal_ctx.append(f"UNVERIFIED funding signal — do not assert.")
    if ls:
        signal_ctx.append(f"VERIFIED: Layoff of {ls.get('laid_off_count')} ({ls.get('percentage')}%) on {ls.get('date')}.")
    total = js.get("total_open_roles", 0)
    ai_roles = js.get("ai_roles", 0)
    if total > 0:
        flag = "VERIFIED" if total >= 5 else "WEAK SIGNAL (< 5 roles — do NOT assert aggressive hiring)"
        signal_ctx.append(f"{flag}: {total} open roles, {ai_roles} AI-adjacent.")
    if ai_score > 0:
        signal_ctx.append(f"AI maturity: {ai_score}/3 ({am.get('confidence','low')} confidence). {am.get('summary','')}")

    honesty = []
    if js.get("total_open_roles", 0) < 5:
        honesty.append("Do NOT say 'scaling aggressively' — fewer than 5 open roles. Ask rather than assert.")
    if icp_result.confidence_label == "low":
        honesty.append("ICP confidence LOW — frame as question/observation, not assertion.")
    if am.get("confidence") == "low" and ai_score >= 2:
        honesty.append("AI maturity is 2+ but LOW confidence — use 'your public profile suggests' not 'you are ready'.")
    if not honesty:
        honesty.append("Signal confidence sufficient — you may assert verified facts directly.")

    seg = icp_result.segment
    seg_prompt = SEGMENT_PROMPTS.get(seg, SEGMENT_PROMPTS[None])

    prompt = f"""You are writing a cold outreach email for Tenacious Consulting and Outsourcing.
{seg_prompt}
{STYLE_GUIDE}

Prospect: {prospect_first_name}{' (' + prospect_title + ')' if prospect_title else ''}
Company: {cb.get('name', 'the company')} | Sector: {cb.get('industry', 'technology')}
Segment: {icp_result.segment_name} | Pitch: {icp_result.pitch_variant} | Confidence: {icp_result.confidence_label}

Signals (ONLY reference VERIFIED ones):
{chr(10).join(signal_ctx) or 'No strong signals verified.'}

Competitor gap finding (weave in if confidence medium/high):
{competitor_brief.get('narrative', 'N/A')}

HONESTY CONSTRAINTS:
{chr(10).join('- ' + h for h in honesty)}

Output format (no markdown, no asterisks):
SUBJECT: <subject line>
BODY:
<email body>"""

    text, usage = chat(messages=[{"role":"user","content":prompt}], temperature=0.4, max_tokens=400, trace_id=trace_id)
    subject, body = "", text
    lines = text.strip().split("\n")

    for i, line in enumerate(lines):
        if _is_marker(line, "SUBJECT:"):
            subject = _clean_marker(line, "SUBJECT:")
            rest = lines[i+1:]
            # Skip BODY: marker line if present
            if rest and _is_marker(rest[0], "BODY:"):
                rest = rest[1:]
            body = "\n".join(rest).strip()
            break

    # Fallback: if no subject found, use first line as subject
    if not subject and lines:
        subject = lines[0].strip().lstrip("*").strip()
        body = "\n".join(lines[1:]).strip()

    # Clean any remaining ** markdown from subject and body
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