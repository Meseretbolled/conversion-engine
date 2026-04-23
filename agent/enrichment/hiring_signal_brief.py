"""
enrichment/hiring_signal_brief.py
Merges all public signals into a structured hiring_signal_brief.json.

Signals and confidence schema:
  crunchbase:        firmographic data — confidence: high/medium/low
  funding_signal:    recent Series A/B — confidence: high/medium/low
  layoff_signal:     recent layoff event — confidence: high/low
  job_signal:        open role velocity — confidence: high (≥5 roles) / low (<5)
  leadership_signal: CTO/VP Eng change — confidence: high/medium/low
  ai_maturity:       0-3 score — confidence: high/medium/low

Every signal carries:
  - "confidence": "high" | "medium" | "low"
  - "evidence": human-readable justification string
"""
import json
from datetime import datetime, timedelta
from typing import Optional

from enrichment.crunchbase import lookup_company
from enrichment.layoffs import check_layoffs
from enrichment.ai_maturity import score_ai_maturity
from enrichment.job_scraper import scrape_jobs_sync
from enrichment.leadership_change import build_leadership_signal

FUNDING_LOOKBACK_DAYS = 180


def _days_since(date_str):
    if not date_str:
        return None
    try:
        d = datetime.fromisoformat(str(date_str).split("T")[0])
        return (datetime.utcnow() - d).days
    except Exception:
        return None


def _is_recent_funding(cb_record):
    last_date = cb_record.get("last_funding_at")
    days = _days_since(last_date)
    funding_type = cb_record.get("last_funding_type", "")
    total = cb_record.get("total_funding_usd")
    recent = days is not None and days <= FUNDING_LOOKBACK_DAYS
    series_ab = any(x in str(funding_type).upper() for x in ["SERIES_A", "SERIES_B", "A", "B"])

    # Confidence: high if we have a date + recent, low if inferred only
    if recent and last_date:
        confidence = "high"
        evidence = f"Closed {funding_type} {days} days ago (within {FUNDING_LOOKBACK_DAYS}-day window). Total funding: ${total:,}" if total else f"Closed {funding_type} {days} days ago."
    elif last_date:
        confidence = "medium"
        evidence = f"Last funding {days} days ago — outside {FUNDING_LOOKBACK_DAYS}-day window."
    else:
        confidence = "low"
        evidence = "No funding date found in Crunchbase record."

    return {
        "last_funding_date": last_date,
        "days_since_funding": days,
        "funding_type": funding_type,
        "total_funding_usd": total,
        "is_recent": recent,
        "is_series_ab": series_ab,
        "confidence": confidence,
        "evidence": evidence,
    }


def build_hiring_signal_brief(
    company_name: str,
    careers_url: Optional[str] = None,
    skip_scraping: bool = False,
) -> dict:
    """
    Build the full hiring signal brief for a prospect company.
    All signals include uniform confidence scores and evidence strings.
    """
    brief = {
        "company": company_name,
        "generated_at": datetime.utcnow().isoformat(),
        "schema_version": "1.1",
        "crunchbase": None,
        "funding_signal": None,
        "layoff_signal": None,
        "job_signal": None,
        "leadership_signal": None,
        "ai_maturity": None,
        "icp_segment_signals": [],
        "errors": [],
    }

    # ── 1. Crunchbase firmographics ─────────────────────────────────────
    cb = None
    try:
        cb = lookup_company(company_name)
        if cb:
            cb["confidence"] = "high" if cb.get("crunchbase_id") else "medium"
            cb["evidence"] = f"Crunchbase ODM record found for '{company_name}'." if cb else f"No exact match for '{company_name}' — partial match used."
        else:
            cb = {
                "confidence": "low",
                "evidence": f"No Crunchbase record found for '{company_name}'.",
            }
        brief["crunchbase"] = cb
    except Exception as e:
        brief["errors"].append(f"crunchbase: {e}")
        brief["crunchbase"] = {"confidence": "low", "evidence": f"Crunchbase lookup error: {e}"}

    # ── 2. Funding signal ───────────────────────────────────────────────
    try:
        if cb and cb.get("last_funding_at"):
            brief["funding_signal"] = _is_recent_funding(cb)
        else:
            brief["funding_signal"] = {
                "is_recent": False,
                "is_series_ab": False,
                "confidence": "low",
                "evidence": "No funding data available in Crunchbase record.",
            }
    except Exception as e:
        brief["errors"].append(f"funding: {e}")

    # ── 3. Layoff signal ────────────────────────────────────────────────
    try:
        layoff = check_layoffs(company_name)
        if layoff:
            layoff["confidence"] = "high" if layoff.get("within_120_days") else "medium"
            layoff["evidence"] = (
                f"Layoff of {layoff.get('laid_off_count', '?')} employees "
                f"({layoff.get('percentage', '?')}%) on {layoff.get('date', '?')} — "
                f"{'within' if layoff.get('within_120_days') else 'outside'} 120-day window."
            )
        else:
            layoff = {
                "confidence": "low",
                "evidence": f"No layoff event found for '{company_name}' in layoffs.fyi dataset.",
            }
        brief["layoff_signal"] = layoff
    except Exception as e:
        brief["errors"].append(f"layoffs: {e}")

    # ── 4. Job post velocity signal ─────────────────────────────────────
    job_signal = None
    if not skip_scraping:
        try:
            job_signal = scrape_jobs_sync(company_name, careers_url)
            total_roles = job_signal.get("total_open_roles", 0)
            job_signal["confidence"] = "high" if total_roles >= 5 else "low"
            job_signal["evidence"] = (
                f"Found {total_roles} open roles ({job_signal.get('engineering_roles', 0)} engineering, "
                f"{job_signal.get('ai_roles', 0)} AI-adjacent). "
                f"{'Strong hiring signal.' if total_roles >= 5 else 'Weak signal — fewer than 5 open roles. Do not assert aggressive hiring.'}"
            )
            brief["job_signal"] = job_signal
        except Exception as e:
            brief["errors"].append(f"job_scraper: {e}")
            brief["job_signal"] = {
                "confidence": "low",
                "evidence": f"Job scraping failed: {e}",
                "total_open_roles": 0,
                "ai_roles": 0,
                "engineering_roles": 0,
            }
    else:
        brief["job_signal"] = {
            "skipped": True,
            "confidence": "low",
            "evidence": "Job scraping skipped (skip_scraping=True).",
            "total_open_roles": 0,
            "ai_roles": 0,
            "engineering_roles": 0,
        }

    # ── 5. Leadership change signal ─────────────────────────────────────
    try:
        leadership = build_leadership_signal(
            company_name=company_name,
            cb_record=cb if cb else None,
        )
        brief["leadership_signal"] = leadership
    except Exception as e:
        brief["errors"].append(f"leadership_change: {e}")
        brief["leadership_signal"] = {
            "detected": False,
            "confidence": "low",
            "evidence": f"Leadership change detection failed: {e}",
        }

    # ── 6. AI maturity scoring ──────────────────────────────────────────
    try:
        js = job_signal or {}
        stack = js.get("detected_stack", [])
        ai_roles = js.get("ai_roles", 0)
        total_eng = js.get("engineering_roles", 0)
        maturity = score_ai_maturity(
            ai_roles=ai_roles,
            total_eng_roles=total_eng,
            has_modern_ml_stack=any(s in stack for s in ["ml", "data"]),
        )
        brief["ai_maturity"] = maturity.to_dict()
    except Exception as e:
        brief["errors"].append(f"ai_maturity: {e}")
        brief["ai_maturity"] = {
            "score": 0,
            "confidence": "low",
            "evidence": f"AI maturity scoring failed: {e}",
        }

    # ── 7. Derive ICP segment signals ───────────────────────────────────
    brief["icp_segment_signals"] = _derive_icp_signals(brief)

    return brief


def _derive_icp_signals(brief):
    signals = []
    fs = brief.get("funding_signal") or {}
    ls = brief.get("layoff_signal") or {}
    ls_change = brief.get("leadership_signal") or {}
    am = brief.get("ai_maturity") or {}

    # Segment 1: Recently funded Series A/B
    if fs.get("is_recent") and fs.get("is_series_ab"):
        signals.append({
            "segment": 1,
            "name": "Recently-funded Series A/B",
            "confidence": fs.get("confidence", "medium"),
            "evidence": fs.get("evidence", ""),
            "rationale": f"Closed {fs.get('funding_type')} {fs.get('days_since_funding')} days ago.",
        })

    # Segment 2: Mid-market restructuring
    if ls.get("within_120_days"):
        signals.append({
            "segment": 2,
            "name": "Mid-market restructuring",
            "confidence": ls.get("confidence", "high"),
            "evidence": ls.get("evidence", ""),
            "rationale": f"Layoff of {ls.get('laid_off_count')} ({ls.get('percentage')}%) on {ls.get('date')}.",
        })

    # Segment 3: Engineering leadership transition
    if ls_change.get("detected") and ls_change.get("within_90_days"):
        signals.append({
            "segment": 3,
            "name": "Engineering-leadership transition",
            "confidence": ls_change.get("confidence", "medium"),
            "evidence": ls_change.get("evidence", ""),
            "rationale": f"New {ls_change.get('title')} appointed {ls_change.get('days_since_appointment')} days ago.",
        })

    # Segment 4: Specialized capability gap
    ai_score = am.get("score", 0)
    if ai_score >= 2:
        signals.append({
            "segment": 4,
            "name": "Specialized capability gap",
            "confidence": am.get("confidence", "low"),
            "evidence": am.get("summary", ""),
            "rationale": f"AI maturity score {ai_score}/3. {am.get('summary', '')}",
        })

    if not signals:
        signals.append({
            "segment": None,
            "name": "Unqualified / needs more data",
            "confidence": "low",
            "evidence": "No qualifying ICP signal found in public data.",
            "rationale": "No strong ICP signal found in public data.",
        })

    return signals


def save_brief(brief: dict, output_path: str):
    with open(output_path, "w") as f:
        json.dump(brief, f, indent=2, default=str)