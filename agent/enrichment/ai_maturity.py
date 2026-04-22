from dataclasses import dataclass, field
from typing import Optional

WEIGHTS = {
    "ai_open_roles_fraction": 3.0,
    "named_ai_leadership":    3.0,
    "github_ai_activity":     2.0,
    "exec_ai_commentary":     2.0,
    "modern_ml_stack":        1.0,
    "strategic_ai_comms":     1.0,
}
MAX_RAW = sum(WEIGHTS.values())

@dataclass
class AIMaturitySignal:
    name: str
    present: bool
    value: Optional[float] = None
    evidence: str = ""
    confidence: str = "low"

@dataclass
class AIMaturityResult:
    score: int
    raw_score: float
    confidence: str
    signals: list = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "confidence": self.confidence,
            "summary": self.summary,
            "signals": [{"name": s.name, "present": s.present, "evidence": s.evidence, "confidence": s.confidence} for s in self.signals],
        }

def score_ai_maturity(ai_roles=0, total_eng_roles=0, has_ai_leadership=False,
                      has_github_ai_activity=False, exec_ai_commentary=False,
                      has_modern_ml_stack=False, strategic_ai_comms=False,
                      evidence_notes=None) -> AIMaturityResult:
    notes = evidence_notes or {}
    signals = []
    raw = 0.0
    high_weight_count = 0

    fraction = (ai_roles / max(total_eng_roles, 1)) if total_eng_roles > 0 else 0
    role_contribution = min(fraction * 10, 1.0) * WEIGHTS["ai_open_roles_fraction"]
    present = ai_roles > 0
    signals.append(AIMaturitySignal(name="ai_open_roles_fraction", present=present, value=fraction,
        evidence=notes.get("ai_roles", f"{ai_roles} AI-adjacent openings out of {total_eng_roles} engineering roles"),
        confidence="high" if total_eng_roles >= 5 else "low"))
    if present:
        raw += role_contribution
        if fraction >= 0.20:
            high_weight_count += 1

    signals.append(AIMaturitySignal(name="named_ai_leadership", present=has_ai_leadership,
        evidence=notes.get("ai_leadership", "Head of AI / VP Data found" if has_ai_leadership else "No named AI leader found publicly"),
        confidence="high" if has_ai_leadership else "medium"))
    if has_ai_leadership:
        raw += WEIGHTS["named_ai_leadership"]
        high_weight_count += 1

    signals.append(AIMaturitySignal(name="github_ai_activity", present=has_github_ai_activity,
        evidence=notes.get("github", "Recent AI/ML commits found" if has_github_ai_activity else "No public AI repos found"),
        confidence="medium"))
    if has_github_ai_activity:
        raw += WEIGHTS["github_ai_activity"]

    signals.append(AIMaturitySignal(name="exec_ai_commentary", present=exec_ai_commentary,
        evidence=notes.get("exec_commentary", "CEO/CTO named AI as strategic" if exec_ai_commentary else "No recent exec AI commentary"),
        confidence="medium"))
    if exec_ai_commentary:
        raw += WEIGHTS["exec_ai_commentary"]

    signals.append(AIMaturitySignal(name="modern_ml_stack", present=has_modern_ml_stack,
        evidence=notes.get("stack", "dbt/Snowflake/Databricks detected" if has_modern_ml_stack else "No ML stack tools detected"),
        confidence="low"))
    if has_modern_ml_stack:
        raw += WEIGHTS["modern_ml_stack"]

    signals.append(AIMaturitySignal(name="strategic_ai_comms", present=strategic_ai_comms,
        evidence=notes.get("comms", "AI in fundraising press" if strategic_ai_comms else "No AI in strategic comms"),
        confidence="low"))
    if strategic_ai_comms:
        raw += WEIGHTS["strategic_ai_comms"]

    ratio = raw / MAX_RAW
    if ratio == 0: score = 0
    elif ratio < 0.25: score = 1
    elif ratio < 0.60: score = 2
    else: score = 3

    active_high = sum(1 for s in signals if s.present and s.confidence == "high")
    if active_high >= 2: confidence = "high"
    elif active_high == 1 or high_weight_count >= 1: confidence = "medium"
    else: confidence = "low"

    active_signals = [s.name for s in signals if s.present]
    if score == 0:
        summary = "No public signal of AI engagement found."
    elif score == 1:
        summary = f"Weak AI signal ({len(active_signals)} low-weight indicators)."
    elif score == 2:
        summary = f"Moderate AI maturity. Multiple public indicators present. Confidence: {confidence}."
    else:
        summary = "Active AI function with strong public commitment."

    return AIMaturityResult(score=score, raw_score=round(raw, 2), confidence=confidence, signals=signals, summary=summary)
