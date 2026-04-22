import json
from datetime import datetime
from typing import Optional
from enrichment.crunchbase import get_all_companies_in_sector
from enrichment.ai_maturity import score_ai_maturity
from agent_core.llm_client import chat

def build_competitor_gap_brief(company_name, sector, prospect_ai_score, prospect_ai_signals, trace_id=None):
    brief = {"company": company_name, "sector": sector, "generated_at": datetime.utcnow().isoformat(),
        "prospect_ai_score": prospect_ai_score, "competitors_analyzed": [],
        "top_quartile_score": None, "sector_median_score": None,
        "prospect_position": None, "gaps": [], "narrative": "", "errors": []}

    peers = get_all_companies_in_sector(sector, limit=20)
    if not peers:
        brief["errors"].append(f"No companies found in sector '{sector}'")
        brief["narrative"] = _fallback(company_name, sector, prospect_ai_score)
        return brief

    scored_peers = []
    for p in peers:
        if p["name"] == company_name:
            continue
        desc = (p.get("description") or "").lower()
        has_ai = any(kw in desc for kw in ["ai","machine learning","ml","data science","nlp"])
        result = score_ai_maturity(has_modern_ml_stack=has_ai, strategic_ai_comms=has_ai)
        scored_peers.append({"name": p["name"], "ai_score": result.score,
            "funding": p.get("total_funding_usd"), "description": p.get("description","")[:200]})

    if not scored_peers:
        brief["narrative"] = _fallback(company_name, sector, prospect_ai_score)
        return brief

    scores = sorted([p["ai_score"] for p in scored_peers], reverse=True)
    n = len(scores)
    top_q = scores[max(0, n//4 - 1)]
    median = scores[n//2]
    brief["competitors_analyzed"] = scored_peers[:10]
    brief["top_quartile_score"] = top_q
    brief["sector_median_score"] = median
    brief["prospect_position"] = "top_quartile" if prospect_ai_score >= top_q else ("above_median" if prospect_ai_score >= median else ("below_median" if prospect_ai_score > 0 else "no_signal"))

    present = {s["name"] for s in prospect_ai_signals if s.get("present")}
    top_peers = [p for p in scored_peers if p["ai_score"] >= top_q][:5]
    gaps = []
    candidates = [
        {"practice":"Dedicated AI/ML leadership hire","signal":"named_ai_leadership","impact":"Top-quartile companies have a named Head of AI or VP Data."},
        {"practice":"Active AI engineering hiring","signal":"ai_open_roles_fraction","impact":"Sector leaders hire ML engineers at 20%+ of engineering openings."},
        {"practice":"Modern ML stack adoption","signal":"modern_ml_stack","impact":"Top peers show public tooling around dbt, Databricks, or model training."},
        {"practice":"Public executive AI commitment","signal":"exec_ai_commentary","impact":"Leading companies have their CEO/CTO publicly committing to AI strategy."},
    ]
    for g in candidates:
        if g["signal"] not in present and len(top_peers) >= 2:
            gaps.append(g)
        if len(gaps) >= 3:
            break
    brief["gaps"] = gaps

    try:
        peer_names = ", ".join(p["name"] for p in top_peers[:3])
        gap_bullets = "\n".join(f"- {g['practice']}: {g['impact']}" for g in gaps)
        prompt = f"""Write 2–3 sentences for a B2B sales email research finding:
Company: {company_name}, Sector: {sector}
Their AI score: {prospect_ai_score}/3, Sector top-quartile: {top_q}/3, Median: {median}/3
Top peers: {peer_names}
Gaps vs top quartile:
{gap_bullets}
Be factual, respectful, grounded. No fluff. Do NOT mention Tenacious Consulting."""
        text, _ = chat(messages=[{"role":"user","content":prompt}], temperature=0.2, max_tokens=200, trace_id=trace_id)
        brief["narrative"] = text.strip()
    except Exception as e:
        brief["errors"].append(f"narrative_llm: {e}")
        brief["narrative"] = _fallback(company_name, sector, prospect_ai_score)
    return brief

def _fallback(company_name, sector, score):
    return (f"Based on public data, {company_name} shows a {score}/3 AI maturity score in the {sector} sector. "
            f"Comparable companies are actively building dedicated AI functions — a gap that typically takes 6–12 months to close.")

def save_brief(brief, output_path):
    with open(output_path, "w") as f:
        json.dump(brief, f, indent=2, default=str)
