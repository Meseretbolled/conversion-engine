"""

API
---
score_ai_maturity(**kwargs) -> AIMaturityResult
    Ingests all six required signal categories, applies explicit tiered weights,
    returns a 0–3 integer score, per-signal justifications, an overall confidence
    label, and a human-readable summary suitable for use in outreach phrasing.

    Inputs (all keyword, all optional, all default to absent/False/0):
        ai_roles          : int   — count of AI-adjacent open roles
        total_eng_roles   : int   — total open engineering roles
        has_ai_leadership : bool  — Head of AI / VP Data / Chief Scientist found
        has_github_ai_activity : bool — recent AI/ML commits on public org repos
        exec_ai_commentary     : bool — CEO/CTO named AI as strategic in last 12mo
        has_modern_ml_stack    : bool — dbt/Snowflake/Databricks/W&B/Ray/vLLM detected
        strategic_ai_comms     : bool — AI named in fundraising press / annual report
        evidence_notes    : dict  — optional override strings per signal key

    Outputs (AIMaturityResult):
        .score     : int   — 0 | 1 | 2 | 3
        .raw_score : float — weighted sum before bucketing
        .confidence: str   — "high" | "medium" | "low"
        .signals   : list[AIMaturitySignal] — per-signal breakdown
        .summary   : str   — human-readable phrase for outreach use
        .to_dict() : dict  — JSON-serialisable representation

Signal Weights (tiered, matching rubric specification)
------------------------------------------------------
HIGH WEIGHT (3.0 points each):
    ai_open_roles_fraction  — AI roles as % of total engineering openings
    named_ai_leadership     — Head of AI / VP Data / Chief Scientist on team page

MEDIUM WEIGHT (2.0 points each):
    github_ai_activity      — recent commits on model training / inference repos
    exec_ai_commentary      — CEO/CTO public AI commitment in last 12 months

LOW WEIGHT (1.0 point each):
    modern_ml_stack         — BuiltWith/Wappalyzer tools: dbt, Databricks, etc.
    strategic_ai_comms      — AI in annual reports / fundraising press

Score Buckets
-------------
    raw = 0          → score 0  (no signal — silent-company path)
    0 < raw < 0.25×MAX → score 1  (weak)
    0.25×MAX ≤ raw < 0.60×MAX → score 2  (moderate)
    raw ≥ 0.60×MAX   → score 3  (active AI function)

    MAX = 12.0 (sum of all weights)

Confidence Label
----------------
    "high"   — ≥ 2 high-weight signals present
    "medium" — exactly 1 high-weight signal, OR ≥ 1 medium-weight signal
    "low"    — only low-weight signals, or no signals at all

Phrasing Contract (used by outreach_composer.py)
-------------------------------------------------
    score 0, confidence any → OMIT AI maturity from email; do not assert
    score ≥1, confidence high  → assert directly ("your public AI team includes...")
    score ≥1, confidence medium → observe ("your public profile suggests...")
    score ≥1, confidence low   → ask ("if AI is a priority for your team...")

Silent-Company Path
-------------------
    When score = 0, .summary explicitly says "No public signal of AI engagement."
    This is a known false-negative path: a sophisticated company may be silent by
    choice. The composer must not penalise absence of signal; it must omit the topic.
"""

from dataclasses import dataclass, field
from typing import Optional

# ── Tiered weights — matches rubric specification exactly ─────────────────────
WEIGHTS: dict[str, float] = {
    # HIGH weight (3.0)
    "ai_open_roles_fraction": 3.0,
    "named_ai_leadership":    3.0,
    # MEDIUM weight (2.0)
    "github_ai_activity":     2.0,
    "exec_ai_commentary":     2.0,
    # LOW weight (1.0)
    "modern_ml_stack":        1.0,
    "strategic_ai_comms":     1.0,
}

WEIGHT_TIER: dict[str, str] = {
    "ai_open_roles_fraction": "high",
    "named_ai_leadership":    "high",
    "github_ai_activity":     "medium",
    "exec_ai_commentary":     "medium",
    "modern_ml_stack":        "low",
    "strategic_ai_comms":     "low",
}

MAX_RAW: float = sum(WEIGHTS.values())   # 12.0

# Score bucket thresholds (fraction of MAX_RAW)
_BUCKET_SCORE_1 = 0.01          # any signal at all
_BUCKET_SCORE_2 = 0.25          # 25% of max
_BUCKET_SCORE_3 = 0.60          # 60% of max


@dataclass
class AIMaturitySignal:
    """One scored signal input."""
    name:        str
    weight_tier: str            # "high" | "medium" | "low"
    weight:      float
    present:     bool
    value:       Optional[float] = None   # numeric value where applicable
    evidence:    str = ""
    confidence:  str = "low"
    justification: str = ""     # why this signal was scored this way


@dataclass
class AIMaturityResult:
    """
    Output of score_ai_maturity().

    score      : 0–3 integer, gates Segment 4 and shifts pitch language
    raw_score  : weighted sum before bucketing (0.0–12.0)
    confidence : "high" | "medium" | "low" — controls phrasing mode
    signals    : per-signal breakdown list
    summary    : one sentence for use in outreach; see phrasing contract above
    """
    score:      int
    raw_score:  float
    confidence: str
    signals:    list = field(default_factory=list)
    summary:    str = ""

    def phrasing_mode(self) -> str:
        """
        Returns the phrasing mode for outreach_composer.py.

        "omit"   — score 0; do not reference AI maturity in email
        "assert" — score ≥ 1, confidence high
        "observe"— score ≥ 1, confidence medium
        "ask"    — score ≥ 1, confidence low
        """
        if self.score == 0:
            return "omit"
        if self.confidence == "high":
            return "assert"
        if self.confidence == "medium":
            return "observe"
        return "ask"

    def to_dict(self) -> dict:
        return {
            "score":        self.score,
            "raw_score":    self.raw_score,
            "confidence":   self.confidence,
            "phrasing_mode": self.phrasing_mode(),
            "summary":      self.summary,
            "signals": [
                {
                    "name":          s.name,
                    "weight_tier":   s.weight_tier,
                    "weight":        s.weight,
                    "present":       s.present,
                    "value":         s.value,
                    "evidence":      s.evidence,
                    "confidence":    s.confidence,
                    "justification": s.justification,
                }
                for s in self.signals
            ],
        }


def score_ai_maturity(
    ai_roles: int = 0,
    total_eng_roles: int = 0,
    has_ai_leadership: bool = False,
    has_github_ai_activity: bool = False,
    exec_ai_commentary: bool = False,
    has_modern_ml_stack: bool = False,
    strategic_ai_comms: bool = False,
    evidence_notes: Optional[dict] = None,
) -> AIMaturityResult:
    """
    Score AI maturity from six public signal categories.

    All parameters are optional; absent signals score 0 for that category.
    See module docstring for full API specification.
    """
    notes = evidence_notes or {}
    signals: list[AIMaturitySignal] = []
    raw: float = 0.0
    high_weight_present: int = 0
    medium_weight_present: int = 0

    # ── Signal 1: AI-adjacent open roles (HIGH weight) ────────────────────────
    fraction = (ai_roles / max(total_eng_roles, 1)) if total_eng_roles > 0 else 0.0
    role_contrib = min(fraction * 10.0, 1.0) * WEIGHTS["ai_open_roles_fraction"]
    role_present = ai_roles > 0
    role_conf = "high" if total_eng_roles >= 5 else ("medium" if total_eng_roles > 0 else "low")
    role_just = (
        f"{ai_roles} AI-adjacent role(s) = {fraction:.0%} of {total_eng_roles} engineering openings. "
        f"{'≥20% fraction meets top-quartile threshold.' if fraction >= 0.20 else 'Below 20% fraction.'}"
        if role_present else
        f"0 AI-adjacent roles found among {total_eng_roles} total engineering openings."
    )
    signals.append(AIMaturitySignal(
        name="ai_open_roles_fraction",
        weight_tier="high", weight=WEIGHTS["ai_open_roles_fraction"],
        present=role_present, value=round(fraction, 3),
        evidence=notes.get("ai_roles", f"{ai_roles} AI-adjacent openings / {total_eng_roles} engineering roles"),
        confidence=role_conf,
        justification=role_just,
    ))
    if role_present:
        raw += role_contrib
        if fraction >= 0.20:
            high_weight_present += 1

    # ── Signal 2: Named AI/ML leadership (HIGH weight) ───────────────────────
    lead_conf = "high" if has_ai_leadership else "medium"
    lead_just = (
        "Head of AI / VP Data / Chief Scientist confirmed on public team page or LinkedIn."
        if has_ai_leadership else
        "No named AI leader found on public team page, LinkedIn, or press. "
        "Absence is not proof of absence — some companies keep this private."
    )
    signals.append(AIMaturitySignal(
        name="named_ai_leadership",
        weight_tier="high", weight=WEIGHTS["named_ai_leadership"],
        present=has_ai_leadership,
        evidence=notes.get("ai_leadership", "Head of AI / VP Data found" if has_ai_leadership else "No named AI leader found publicly"),
        confidence=lead_conf,
        justification=lead_just,
    ))
    if has_ai_leadership:
        raw += WEIGHTS["named_ai_leadership"]
        high_weight_present += 1

    # ── Signal 3: Public GitHub org AI activity (MEDIUM weight) ──────────────
    gh_conf = "medium"
    gh_just = (
        "Recent commits on repos involving model training, inference, or AI tooling found on public org."
        if has_github_ai_activity else
        "No public AI repos found. Absence is not proof of absence — many companies keep AI work private."
    )
    signals.append(AIMaturitySignal(
        name="github_ai_activity",
        weight_tier="medium", weight=WEIGHTS["github_ai_activity"],
        present=has_github_ai_activity,
        evidence=notes.get("github", "Recent AI/ML commits found" if has_github_ai_activity else "No public AI repos found"),
        confidence=gh_conf,
        justification=gh_just,
    ))
    if has_github_ai_activity:
        raw += WEIGHTS["github_ai_activity"]
        medium_weight_present += 1

    # ── Signal 4: Executive AI commentary (MEDIUM weight) ─────────────────────
    exec_conf = "medium"
    exec_just = (
        "CEO or CTO named AI as a strategic priority in posts, keynotes, or interviews in the last 12 months."
        if exec_ai_commentary else
        "No recent CEO/CTO AI commentary found in public posts, keynotes, or press coverage."
    )
    signals.append(AIMaturitySignal(
        name="exec_ai_commentary",
        weight_tier="medium", weight=WEIGHTS["exec_ai_commentary"],
        present=exec_ai_commentary,
        evidence=notes.get("exec_commentary", "CEO/CTO named AI as strategic" if exec_ai_commentary else "No recent exec AI commentary"),
        confidence=exec_conf,
        justification=exec_just,
    ))
    if exec_ai_commentary:
        raw += WEIGHTS["exec_ai_commentary"]
        medium_weight_present += 1

    # ── Signal 5: Modern data/ML stack (LOW weight) ───────────────────────────
    stack_just = (
        "BuiltWith or Wappalyzer detected modern ML tools: dbt, Snowflake, Databricks, W&B, Ray, or vLLM."
        if has_modern_ml_stack else
        "No ML stack tools detected via BuiltWith/Wappalyzer. Low-weight signal only."
    )
    signals.append(AIMaturitySignal(
        name="modern_ml_stack",
        weight_tier="low", weight=WEIGHTS["modern_ml_stack"],
        present=has_modern_ml_stack,
        evidence=notes.get("stack", "dbt/Snowflake/Databricks detected" if has_modern_ml_stack else "No ML stack tools detected"),
        confidence="low",
        justification=stack_just,
    ))
    if has_modern_ml_stack:
        raw += WEIGHTS["modern_ml_stack"]

    # ── Signal 6: Strategic AI communications (LOW weight) ────────────────────
    comms_just = (
        "AI positioned as a company priority in annual reports, fundraising press, or investor letters."
        if strategic_ai_comms else
        "No AI framing found in annual reports, investor letters, or fundraising press releases."
    )
    signals.append(AIMaturitySignal(
        name="strategic_ai_comms",
        weight_tier="low", weight=WEIGHTS["strategic_ai_comms"],
        present=strategic_ai_comms,
        evidence=notes.get("comms", "AI in fundraising press" if strategic_ai_comms else "No AI in strategic comms"),
        confidence="low",
        justification=comms_just,
    ))
    if strategic_ai_comms:
        raw += WEIGHTS["strategic_ai_comms"]

    # ── Score bucketing ───────────────────────────────────────────────────────
    ratio = raw / MAX_RAW
    if ratio == 0.0:
        score = 0
    elif ratio < _BUCKET_SCORE_2:
        score = 1
    elif ratio < _BUCKET_SCORE_3:
        score = 2
    else:
        score = 3

    # ── Confidence label ──────────────────────────────────────────────────────
    if high_weight_present >= 2:
        confidence = "high"
    elif high_weight_present == 1 or medium_weight_present >= 1:
        confidence = "medium"
    else:
        confidence = "low"

    # ── Summary (phrasing-safe, used directly in outreach) ───────────────────
    active = [s for s in signals if s.present]

    if score == 0:
        # Silent-company path — explicit 0 with explanation
        summary = (
            "No public signal of AI engagement found. "
            "The company may be intentionally silent or early-stage on AI. "
            "Do not reference AI maturity in outreach — ask rather than assert."
        )
    elif score == 1:
        names = ", ".join(s.name.replace("_", " ") for s in active)
        summary = (
            f"Weak AI signal: {len(active)} low-weight indicator(s) present ({names}). "
            f"Confidence: {confidence}. Use exploratory language — ask rather than assert."
        )
    elif score == 2:
        names = ", ".join(s.name.replace("_", " ") for s in active)
        summary = (
            f"Moderate AI maturity: {len(active)} signal(s) active ({names}). "
            f"Confidence: {confidence}. "
            + ("Assert directly." if confidence == "high" else
               "Observe ('your public profile suggests...') — avoid strong assertions.")
        )
    else:
        summary = (
            f"Active AI function: {len(active)} signal(s) including high-weight indicators. "
            f"Confidence: {confidence}. "
            + ("Assert directly — company shows strong public AI commitment." if confidence == "high"
               else "Strong score but mixed confidence — use 'your public AI investment suggests...'")
        )

    return AIMaturityResult(
        score=score,
        raw_score=round(raw, 2),
        confidence=confidence,
        signals=signals,
        summary=summary,
    )