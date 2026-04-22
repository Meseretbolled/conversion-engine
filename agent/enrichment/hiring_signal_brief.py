import json
from datetime import datetime, timedelta
from typing import Optional
from enrichment.crunchbase import lookup_company
from enrichment.layoffs import check_layoffs
from enrichment.ai_maturity import score_ai_maturity
from enrichment.job_scraper import scrape_jobs_sync

FUNDING_LOOKBACK_DAYS = 180

def _days_since(date_str):
    if not date_str:
        return None
    try:
        d = datetime.fromisoformat(str(date_str).split("T")[0])
        return (datetime.utcnow() - d).days
    except:
        return None

def _is_recent_funding(cb_record):
    last_date = cb_record.get("last_funding_at")
    days = _days_since(last_date)
    funding_type = cb_record.get("last_funding_type", "")
    total = cb_record.get("total_funding_usd")
    recent = days is not None and days <= FUNDING_LOOKBACK_DAYS
    series_ab = any(x in str(funding_type).upper() for x in ["SERIES_A","SERIES_B","A","B"])
    return {
        "last_funding_date": last_date, "days_since_funding": days,
        "funding_type": funding_type, "total_funding_usd": total,
        "is_recent": recent, "is_series_ab": series_ab,
        "confidence": "high" if (recent and last_date) else "low",
    }

def build_hiring_signal_brief(company_name, careers_url=None, skip_scraping=False):
    brief = {"company": company_name, "generated_at": datetime.utcnow().isoformat(),
        "crunchbase": None, "funding_signal": None, "layoff_signal": None,
        "job_signal": None, "leadership_signal": None, "ai_maturity": None,
        "icp_segment_signals": [], "errors": []}

    try:
        cb = lookup_company(company_name)
        brief["crunchbase"] = cb
        if cb:
            brief["funding_signal"] = _is_recent_funding(cb)
    except Exception as e:
        brief["errors"].append(f"crunchbase: {e}")

    try:
        layoff = check_layoffs(company_name)
        brief["layoff_signal"] = layoff
    except Exception as e:
        brief["errors"].append(f"layoffs: {e}")

    job_signal = None
    if not skip_scraping:
        try:
            job_signal = scrape_jobs_sync(company_name, careers_url)
            brief["job_signal"] = job_signal
        except Exception as e:
            brief["errors"].append(f"job_scraper: {e}")
    else:
        brief["job_signal"] = {"skipped": True, "reason": "skip_scraping=True"}

    try:
        js = job_signal or {}
        stack = js.get("detected_stack", [])
        ai_roles = js.get("ai_roles", 0)
        total_eng = js.get("engineering_roles", 0)
        maturity = score_ai_maturity(ai_roles=ai_roles, total_eng_roles=total_eng,
            has_modern_ml_stack=any(s in stack for s in ["ml","data"]))
        brief["ai_maturity"] = maturity.to_dict()
    except Exception as e:
        brief["errors"].append(f"ai_maturity: {e}")

    brief["icp_segment_signals"] = _derive_icp_signals(brief)
    return brief

def _derive_icp_signals(brief):
    signals = []
    fs = brief.get("funding_signal") or {}
    ls = brief.get("layoff_signal")
    am = brief.get("ai_maturity") or {}
    if fs.get("is_recent") and fs.get("is_series_ab"):
        signals.append({"segment": 1, "name": "Recently-funded Series A/B",
            "confidence": fs.get("confidence","medium"),
            "rationale": f"Closed {fs.get('funding_type')} {fs.get('days_since_funding')} days ago."})
    if ls and ls.get("within_120_days"):
        signals.append({"segment": 2, "name": "Mid-market restructuring", "confidence": "high",
            "rationale": f"Layoff of {ls.get('laid_off_count')} ({ls.get('percentage')}%) on {ls.get('date')}."})
    ai_score = am.get("score", 0)
    if ai_score >= 2:
        signals.append({"segment": 4, "name": "Specialized capability gap",
            "confidence": am.get("confidence","low"),
            "rationale": f"AI maturity score {ai_score}/3. {am.get('summary','')}"})
    if not signals:
        signals.append({"segment": None, "name": "Unqualified / needs more data",
            "confidence": "low", "rationale": "No strong ICP signal found in public data."})
    return signals

def save_brief(brief, output_path):
    with open(output_path, "w") as f:
        json.dump(brief, f, indent=2, default=str)
