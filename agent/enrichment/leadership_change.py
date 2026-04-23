"""
enrichment/leadership_change.py
Detects recent CTO/VP Engineering transitions from Crunchbase and press signals.

Signal source: Crunchbase ODM 'people' field + press release text patterns.
Lookback window: 90 days (Segment 3 qualifying filter).

Per-signal confidence:
- "high"   → found in Crunchbase with explicit title + date
- "medium" → inferred from press release keyword match
- "low"    → no signal found
"""
import re
from datetime import datetime, timedelta
from typing import Optional

# Titles that qualify as engineering leadership transitions
LEADERSHIP_TITLES = [
    "cto", "chief technology officer",
    "vp engineering", "vp of engineering",
    "vice president engineering", "vice president of engineering",
    "head of engineering", "svp engineering",
    "chief architect",
]

LOOKBACK_DAYS = 90


def _days_since(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        d = datetime.fromisoformat(str(date_str).split("T")[0])
        return (datetime.utcnow() - d).days
    except Exception:
        return None


def detect_from_crunchbase(cb_record: Optional[dict]) -> dict:
    """
    Detect leadership change from Crunchbase ODM record.
    Looks for 'people' or 'leadership' field with recent CTO/VP Eng appointments.

    Returns signal dict with confidence score.
    """
    result = {
        "signal": "leadership_change",
        "detected": False,
        "title": None,
        "name": None,
        "days_since_appointment": None,
        "within_90_days": False,
        "confidence": "low",
        "source": "crunchbase_odm",
        "evidence": "No leadership change signal found in Crunchbase record.",
    }

    if not cb_record:
        return result

    # Check various Crunchbase field names for leadership data
    people = (
        cb_record.get("people") or
        cb_record.get("leadership") or
        cb_record.get("executives") or
        []
    )

    if isinstance(people, str):
        # Some ODM exports have people as a comma-separated string
        people = [{"title": p.strip()} for p in people.split(",")]

    if not isinstance(people, list):
        return result

    for person in people:
        if not isinstance(person, dict):
            continue
        title = str(person.get("title", "")).lower()
        started = person.get("started_on") or person.get("start_date") or person.get("created_at")

        is_leadership = any(t in title for t in LEADERSHIP_TITLES)
        if not is_leadership:
            continue

        days = _days_since(started)
        within_window = days is not None and days <= LOOKBACK_DAYS

        if within_window:
            result.update({
                "detected": True,
                "title": person.get("title"),
                "name": person.get("name") or person.get("full_name"),
                "days_since_appointment": days,
                "within_90_days": True,
                "confidence": "high" if days is not None else "medium",
                "source": "crunchbase_odm",
                "evidence": (
                    f"{person.get('name', 'Unknown')} appointed as {person.get('title')} "
                    f"{days} days ago (within 90-day Segment 3 window)."
                    if days is not None
                    else f"Recent {person.get('title')} appointment found in Crunchbase."
                ),
            })
            return result

    return result


def detect_from_press_text(company_name: str, press_text: str) -> dict:
    """
    Detect leadership change from press release or news text.
    Uses keyword pattern matching — medium confidence.
    """
    result = {
        "signal": "leadership_change",
        "detected": False,
        "title": None,
        "name": None,
        "days_since_appointment": None,
        "within_90_days": None,
        "confidence": "low",
        "source": "press_text",
        "evidence": "No leadership change signal found in press text.",
    }

    if not press_text:
        return result

    text_lower = press_text.lower()

    # Patterns: "appoints new CTO", "names VP Engineering", "joins as CTO"
    appointment_patterns = [
        r"appoint(?:s|ed|ing)\s+(?:new\s+)?(\w+\s+\w+)\s+as\s+(cto|vp\s+engineering|chief\s+technology)",
        r"(\w+\s+\w+)\s+(?:joins|named|promoted)\s+as\s+(cto|vp\s+engineering|chief\s+technology)",
        r"new\s+(cto|vp\s+engineering|chief\s+technology\s+officer)",
        r"(cto|vp\s+engineering)\s+(?:hire|appointment|transition)",
    ]

    for pattern in appointment_patterns:
        match = re.search(pattern, text_lower)
        if match:
            result.update({
                "detected": True,
                "title": "CTO/VP Engineering (inferred from press)",
                "confidence": "medium",
                "source": "press_text",
                "evidence": f"Leadership appointment keyword found in press text for {company_name}.",
            })
            return result

    return result


def build_leadership_signal(
    company_name: str,
    cb_record: Optional[dict] = None,
    press_text: Optional[str] = None,
) -> dict:
    """
    Main entry point. Combines Crunchbase and press signals.
    Returns the highest-confidence signal found.
    """
    cb_signal = detect_from_crunchbase(cb_record)
    press_signal = detect_from_press_text(company_name, press_text or "")

    # Return highest confidence signal
    confidence_rank = {"high": 3, "medium": 2, "low": 1}

    if cb_signal["detected"] and confidence_rank[cb_signal["confidence"]] >= confidence_rank[press_signal.get("confidence", "low")]:
        return cb_signal
    elif press_signal["detected"]:
        return press_signal
    else:
        return {
            "signal": "leadership_change",
            "detected": False,
            "title": None,
            "name": None,
            "days_since_appointment": None,
            "within_90_days": False,
            "confidence": "low",
            "source": "no_signal",
            "evidence": f"No CTO/VP Engineering transition found for {company_name} in last {LOOKBACK_DAYS} days.",
        }