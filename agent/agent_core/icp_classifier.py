"""
agent/agent_core/icp_classifier.py
ICP segment classifier for Tenacious Conversion Engine.

Classification rules (from seed/icp_definition.md):
1. Layoff in 120 days AND fresh funding → Segment 2 (cost pressure dominates)
2. New CTO/VP Eng in 90 days → Segment 3 (transition window dominates)
3. Capability gap AND AI maturity ≥ 2 → Segment 4
4. Fresh funding in 180 days → Segment 1
5. Otherwise → abstain (None)

Disqualifiers:
- Segment 2: layoff > 40% → abstain (survival mode)
- Segment 4: AI maturity < 2 → abstain
- Confidence < 0.6 → abstain (per icp_definition.md)
"""
from dataclasses import dataclass
from typing import Optional

SEGMENT_NAMES = {
    1: "Recently-funded Series A/B",
    2: "Mid-market restructuring",
    3: "Engineering-leadership transition",
    4: "Specialized capability gap",
}

PITCH_VARIANTS = {
    (1, True):  "scale_ai_team",
    (1, False): "first_ai_function",
    (2, True):  "offshore_ai_cost",
    (2, False): "offshore_cost",
    (3, None):  "leadership_reassessment",
    (4, None):  "ml_project_consulting",
}


@dataclass
class ICPResult:
    segment: Optional[int]
    segment_name: str
    confidence: float
    confidence_label: str
    rationale: str
    disqualified: bool = False
    disqualification_reason: str = ""
    pitch_variant: str = ""

    def to_dict(self):
        return {
            "segment": self.segment,
            "segment_name": self.segment_name,
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "rationale": self.rationale,
            "disqualified": self.disqualified,
            "disqualification_reason": self.disqualification_reason,
            "pitch_variant": self.pitch_variant,
        }


def _c(label: str) -> float:
    return {"low": 0.35, "medium": 0.65, "high": 0.85}.get(label, 0.5)


def _find(signals: list, segment: int) -> Optional[dict]:
    return next((s for s in signals if s.get("segment") == segment), None)


def _abstain(reason: str) -> ICPResult:
    return ICPResult(
        segment=None,
        segment_name="Unqualified",
        confidence=0.0,
        confidence_label="low",
        rationale=reason,
        disqualified=True,
        disqualification_reason=reason,
    )


def _extract_raw_signals(brief: dict) -> dict:
    """
    Extract signals directly from raw brief fields.
    Used as fallback when icp_segment_signals is empty.
    Returns dict with keys: layoff, funding, leadership, ai_maturity
    """
    fs = brief.get("funding_signal") or {}
    ls = brief.get("layoff_signal") or {}
    lc = brief.get("leadership_signal") or {}
    am = brief.get("ai_maturity") or {}
    js = brief.get("job_signal") or {}

    return {
        "has_layoff": bool(ls.get("within_120_days")),
        "layoff_pct": float(ls.get("percentage", 0)),
        "layoff_confidence": ls.get("confidence", "low"),
        "layoff_rationale": ls.get("evidence", f"Layoff of {ls.get('laid_off_count', '?')} on {ls.get('date', '?')}"),

        "has_funding": bool(fs.get("is_recent") and fs.get("is_series_ab")),
        "funding_confidence": fs.get("confidence", "low"),
        "funding_rationale": fs.get("evidence", f"Closed {fs.get('funding_type', '?')} {fs.get('days_since_funding', '?')} days ago"),

        "has_leadership": bool(lc.get("detected") and lc.get("within_90_days")),
        "leadership_confidence": lc.get("confidence", "low"),
        "leadership_rationale": lc.get("evidence", f"New {lc.get('title', '?')} {lc.get('days_since_appointment', '?')} days ago"),

        "ai_score": int(am.get("score", 0)),
        "ai_confidence": am.get("confidence", "low"),
        "ai_rationale": am.get("summary", f"AI maturity {am.get('score', 0)}/3"),

        "open_roles": int(js.get("total_open_roles", 0)),
        "roles_confidence": js.get("confidence", "low"),
    }


def classify(hiring_signal_brief: dict) -> ICPResult:
    """
    Classify a prospect into one of 4 ICP segments or abstain.

    Priority order per icp_definition.md:
    1. Layoff + funding conflict → Segment 2
    2. New CTO/VP Eng → Segment 3
    3. AI capability gap (score ≥ 2) → Segment 4
    4. Fresh funding → Segment 1
    5. Abstain
    """
    am = hiring_signal_brief.get("ai_maturity") or {}
    ai_score = int(am.get("score", 0))
    ai_confidence = am.get("confidence", "low")
    ai_high = ai_score >= 2

    # Try pre-computed icp_segment_signals first
    icp_signals = hiring_signal_brief.get("icp_segment_signals", [])

    if icp_signals:
        return _classify_from_signals(icp_signals, ai_score, ai_confidence, ai_high, hiring_signal_brief)
    else:
        # Fallback: read raw signals directly from brief
        return _classify_from_raw(hiring_signal_brief, ai_score, ai_confidence, ai_high)


def _classify_from_signals(icp_signals, ai_score, ai_confidence, ai_high, brief):
    """Classify using pre-computed icp_segment_signals list."""
    fs = brief.get("funding_signal") or {}

    # Rule 1: Segment 3 takes priority over 2
    seg3 = _find(icp_signals, 3)
    if seg3:
        return ICPResult(
            segment=3,
            segment_name=SEGMENT_NAMES[3],
            confidence=_c(seg3["confidence"]),
            confidence_label=seg3["confidence"],
            rationale=seg3.get("rationale", "Leadership transition detected"),
            pitch_variant=PITCH_VARIANTS[(3, None)],
        )

    # Rule 2: Segment 2 (cost pressure)
    seg2 = _find(icp_signals, 2)
    if seg2:
        # Disqualifier: layoff > 40%
        ls = brief.get("layoff_signal") or {}
        pct = float(ls.get("percentage", 0))
        if pct > 0.40:
            return _abstain(f"Segment 2 disqualified — layoff {pct*100:.0f}% exceeds 40% threshold (survival mode).")

        # Conflict: funded + layoff → Segment 2 still wins per rule 1
        note = ""
        if fs.get("is_recent") and fs.get("is_series_ab"):
            note = " NOTE: conflicting funding signal — cost pressure dominates per classification rules."
        return ICPResult(
            segment=2,
            segment_name=SEGMENT_NAMES[2],
            confidence=_c(seg2["confidence"]),
            confidence_label=seg2["confidence"],
            rationale=seg2.get("rationale", "Layoff signal") + note,
            pitch_variant=PITCH_VARIANTS[(2, ai_high)],
        )

    # Rule 3: Segment 4 (AI capability gap)
    if ai_score >= 2:
        return ICPResult(
            segment=4,
            segment_name=SEGMENT_NAMES[4],
            confidence=_c(ai_confidence),
            confidence_label=ai_confidence,
            rationale=f"AI maturity score {ai_score}/3 ({ai_confidence} confidence). {am.get('summary', '')}",
            pitch_variant=PITCH_VARIANTS[(4, None)],
        )

    # Rule 4: Segment 1 (fresh funding)
    seg1 = _find(icp_signals, 1)
    if seg1:
        return ICPResult(
            segment=1,
            segment_name=SEGMENT_NAMES[1],
            confidence=_c(seg1["confidence"]),
            confidence_label=seg1["confidence"],
            rationale=seg1.get("rationale", "Recent Series A/B funding"),
            pitch_variant=PITCH_VARIANTS[(1, ai_high)],
        )

    return _abstain("No qualifying ICP signal found in public data.")


def _classify_from_raw(brief, ai_score, ai_confidence, ai_high):
    """
    Classify by reading raw signal fields directly.
    Used when icp_segment_signals is empty (e.g. in adversarial probes).
    """
    s = _extract_raw_signals(brief)

    # Disqualifier: layoff > 40%
    if s["has_layoff"] and s["layoff_pct"] > 0.40:
        return _abstain(
            f"Segment 2 disqualified — layoff {s['layoff_pct']*100:.0f}% exceeds 40% (survival mode)."
        )

    # Disqualifier: low confidence layoff → do not assert
    if s["has_layoff"] and s["layoff_confidence"] == "low":
        return _abstain(
            "Layoff signal confidence too low to assert. Do not reference layoff in outreach."
        )

    # Rule 2: New CTO/VP Eng in 90 days → Segment 3 (takes priority over Segment 2)
    if s["has_leadership"]:
        return ICPResult(
            segment=3,
            segment_name=SEGMENT_NAMES[3],
            confidence=_c(s["leadership_confidence"]),
            confidence_label=s["leadership_confidence"],
            rationale=s["leadership_rationale"],
            pitch_variant=PITCH_VARIANTS[(3, None)],
        )

    # Rule 1: Layoff in 120 days → Segment 2 (checked after leadership)
    if s["has_layoff"]:
        note = ""
        if s["has_funding"]:
            note = " NOTE: conflicting funding signal — cost pressure dominates."
        return ICPResult(
            segment=2,
            segment_name=SEGMENT_NAMES[2],
            confidence=_c(s["layoff_confidence"]),
            confidence_label=s["layoff_confidence"],
            rationale=s["layoff_rationale"] + note,
            pitch_variant=PITCH_VARIANTS[(2, ai_high)],
        )

    # Rule 3: AI capability gap → Segment 4
    if ai_score >= 2:
        return ICPResult(
            segment=4,
            segment_name=SEGMENT_NAMES[4],
            confidence=_c(ai_confidence),
            confidence_label=ai_confidence,
            rationale=s["ai_rationale"],
            pitch_variant=PITCH_VARIANTS[(4, None)],
        )

    # Rule 4: Fresh funding → Segment 1
    if s["has_funding"]:
        # Low confidence funding → lower overall confidence
        conf = s["funding_confidence"]
        return ICPResult(
            segment=1,
            segment_name=SEGMENT_NAMES[1],
            confidence=_c(conf),
            confidence_label=conf,
            rationale=s["funding_rationale"],
            pitch_variant=PITCH_VARIANTS[(1, ai_high)],
        )

    return _abstain("No qualifying ICP signal found in public data.")