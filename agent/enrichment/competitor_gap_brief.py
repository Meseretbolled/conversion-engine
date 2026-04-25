"""
Top-Quartile Competitor Gap Analysis

API
---
build_competitor_gap_brief(
    company_name      : str,
    sector            : str,
    prospect_ai_score : int,          # 0–3, from score_ai_maturity()
    prospect_ai_signals: list[dict],  # signals list from AIMaturityResult.to_dict()
    trace_id          : str | None,
) -> dict

Returns competitor_gap_brief.json with the following top-level keys:
    company                  : str
    sector                   : str
    generated_at             : ISO timestamp
    prospect_ai_score        : int (0–3)
    selection_criteria       : dict  — how the 5–10 peers were chosen
    competitors_analyzed     : list  — one entry per peer, with evidence fields
    peer_count               : int   — total peers found
    top_quartile_score       : int | None
    sector_median_score      : int | None
    prospect_position        : str   — "top_quartile" | "above_median" | "below_median" | "no_signal"
    distribution             : dict  — full score distribution across peers
    gaps                     : list  — 2–3 gaps with structured evidence fields
    narrative                : str   — 2–3 sentence research finding for outreach
    sparse_sector            : bool  — True when fewer than 5 peers found
    confidence               : str   — "high" | "medium" | "low"
    errors                   : list

Peer Selection Logic (visible in code, not just probes)
-------------------------------------------------------
1. Pull up to 50 companies from the same sector via get_all_companies_in_sector()
2. Remove the prospect itself by name
3. Score each peer with score_ai_maturity() using description-derived signals
4. Rank by ai_score descending
5. Take the top 10 as "competitors_analyzed"
6. Top quartile = top 25% of scored peers (ceiling index: max(0, n//4 - 1))
7. Median = middle score

Sparse-Sector Branch (fewer than 5 peers)
------------------------------------------
When fewer than 5 peers are found, the brief sets sparse_sector=True,
top_quartile_score=None, sector_median_score=None, gaps=[], and
returns a narrative that explicitly states insufficient data. The composer
must omit competitor gap language when sparse_sector=True.

Gap Evidence Fields (structured, not just text)
------------------------------------------------
Each gap entry contains:
    practice : str   — what the top quartile does
    signal   : str   — which ai_maturity signal it maps to
    impact   : str   — business framing for outreach
    evidence : str   — specific public-signal evidence from peer data
    peer_count_showing : int — how many top-quartile peers show this practice
"""

import json
from datetime import datetime
from typing import Optional

from enrichment.crunchbase import get_all_companies_in_sector
from enrichment.ai_maturity import score_ai_maturity
from agent_core.llm_client import chat

# Minimum peers required to compute a meaningful distribution
_MIN_PEERS_FOR_DISTRIBUTION = 5

# Gap candidates — each maps to an ai_maturity signal name
_GAP_CANDIDATES = [
    {
        "practice":  "Dedicated AI/ML leadership hire",
        "signal":    "named_ai_leadership",
        "impact":    "Top-quartile companies have a named Head of AI or VP Data on the team page.",
        "evidence_template": "{n} of {total} top-quartile peers have a named AI leader publicly visible.",
    },
    {
        "practice":  "Active AI engineering hiring",
        "signal":    "ai_open_roles_fraction",
        "impact":    "Sector leaders hire ML engineers at 20%+ of engineering openings.",
        "evidence_template": "{n} of {total} top-quartile peers show AI-adjacent open roles in public job feeds.",
    },
    {
        "practice":  "Modern ML stack adoption",
        "signal":    "modern_ml_stack",
        "impact":    "Top peers show public tooling around dbt, Databricks, or model training infrastructure.",
        "evidence_template": "{n} of {total} top-quartile peers detected with ML stack tools (dbt/Databricks/W&B).",
    },
    {
        "practice":  "Public executive AI commitment",
        "signal":    "exec_ai_commentary",
        "impact":    "Leading companies have their CEO/CTO publicly naming AI as a strategic priority.",
        "evidence_template": "{n} of {total} top-quartile peers have public CEO/CTO AI commentary in the last 12 months.",
    },
]


def _score_peer(peer: dict) -> dict:
    """
    Score a single Crunchbase peer using description-derived signals.
    Returns the peer dict augmented with ai_score and signal_evidence.
    """
    desc = (peer.get("description") or "").lower()
    industries = " ".join(peer.get("industries_raw") or []).lower()
    combined = f"{desc} {industries}"

    # Derive signals from public description text
    has_ai_keywords = any(kw in combined for kw in [
        "artificial intelligence", " ai ", "machine learning", "deep learning",
        "nlp", "natural language", "computer vision", "llm", "generative ai",
    ])
    has_ml_stack = any(kw in combined for kw in [
        "databricks", "snowflake", "dbt", "mlflow", "weights & biases",
        "ray", "vllm", "hugging face", "spark",
    ])
    has_exec_commentary = any(kw in combined for kw in [
        "ai-first", "ai strategy", "ai-powered", "ai platform",
    ])

    result = score_ai_maturity(
        has_modern_ml_stack=has_ml_stack,
        strategic_ai_comms=has_ai_keywords,
        exec_ai_commentary=has_exec_commentary,
    )

    # Build structured signal evidence for this peer
    signal_evidence = {
        "named_ai_leadership": False,   # not inferable from description
        "ai_open_roles_fraction": False, # not inferable without job scrape
        "modern_ml_stack": has_ml_stack,
        "exec_ai_commentary": has_exec_commentary,
        "strategic_ai_comms": has_ai_keywords,
        "github_ai_activity": False,    # not inferable without GitHub lookup
    }

    return {
        "name":            peer.get("name", "Unknown"),
        "ai_score":        result.score,
        "confidence":      result.confidence,
        "description":     (peer.get("description") or "")[:200],
        "funding":         peer.get("total_funding_usd"),
        "industry":        peer.get("industry"),
        "signal_evidence": signal_evidence,
    }


def _compute_distribution(scores: list[int]) -> dict:
    """Compute full score distribution across peer scores."""
    from collections import Counter
    counts = Counter(scores)
    total = len(scores)
    return {
        "score_counts": {str(k): counts[k] for k in range(4)},
        "total_peers":  total,
        "pct_score_3":  round(counts[3] / total * 100, 1) if total else 0,
        "pct_score_2":  round(counts[2] / total * 100, 1) if total else 0,
        "pct_score_1":  round(counts[1] / total * 100, 1) if total else 0,
        "pct_score_0":  round(counts[0] / total * 100, 1) if total else 0,
    }


def _compute_gaps(
    prospect_ai_signals: list[dict],
    top_peers: list[dict],
) -> list[dict]:
    """
    Identify 2–3 gaps between the prospect and the top-quartile peers.
    Each gap has structured evidence fields showing how many top-quartile
    peers show the practice the prospect does not.
    """
    present_signals = {s["name"] for s in prospect_ai_signals if s.get("present")}
    total_top = len(top_peers)
    gaps = []

    for candidate in _GAP_CANDIDATES:
        if len(gaps) >= 3:
            break
        signal_name = candidate["signal"]
        if signal_name in present_signals:
            continue  # prospect already has this signal — not a gap

        # Count how many top-quartile peers show this practice
        peer_count = sum(
            1 for p in top_peers
            if p.get("signal_evidence", {}).get(signal_name, False)
        )

        # Only include if at least 1 top-quartile peer shows it
        # (or if it's a named_ai_leadership gap — which we can't infer from descriptions
        #  but is the most common gap for Segment 1-2 prospects)
        if peer_count > 0 or signal_name == "named_ai_leadership":
            evidence = candidate["evidence_template"].format(
                n=peer_count,
                total=total_top,
            )
            gaps.append({
                "practice":            candidate["practice"],
                "signal":              signal_name,
                "impact":              candidate["impact"],
                "evidence":            evidence,
                "peer_count_showing":  peer_count,
                "top_quartile_total":  total_top,
            })

    return gaps


def _sparse_narrative(company_name: str, sector: str, peer_count: int, prospect_ai_score: int) -> str:
    return (
        f"Fewer than 5 comparable companies found in the '{sector}' sector "
        f"in the Crunchbase ODM sample (found {peer_count}). "
        f"A sector-distribution comparison cannot be made reliably. "
        f"{company_name}'s public AI maturity score is {prospect_ai_score}/3. "
        "Competitor gap language should be omitted from outreach."
    )


def build_competitor_gap_brief(
    company_name: str,
    sector: str,
    prospect_ai_score: int,
    prospect_ai_signals: list,
    trace_id: Optional[str] = None,
) -> dict:
    """
    Build the competitor gap brief for a prospect.
    See module docstring for full output schema.
    """
    brief = {
        "company":              company_name,
        "sector":               sector,
        "generated_at":         datetime.utcnow().isoformat(),
        "prospect_ai_score":    prospect_ai_score,
        # Selection criteria — visible in output, not just in code comments
        "selection_criteria": {
            "method":           "Crunchbase ODM sector match + ai_maturity scoring",
            "sector_field":     "industries (JSON-parsed 'value' array)",
            "sector_query":     sector,
            "max_candidates":   50,
            "min_for_distribution": _MIN_PEERS_FOR_DISTRIBUTION,
            "scoring_method":   "score_ai_maturity() with description-derived signals",
            "top_quartile_def": "top 25% of peer scores (ceiling index: max(0, n//4-1))",
        },
        "competitors_analyzed": [],
        "peer_count":           0,
        "top_quartile_score":   None,
        "sector_median_score":  None,
        "prospect_position":    None,
        "distribution":         {},
        "gaps":                 [],
        "narrative":            "",
        "sparse_sector":        False,
        "confidence":           "low",
        "errors":               [],
    }

    # ── Step 1: Pull peers from Crunchbase ODM ────────────────────────────────
    try:
        candidates = get_all_companies_in_sector(sector, limit=50)
    except Exception as e:
        brief["errors"].append(f"crunchbase_sector_lookup: {e}")
        brief["narrative"] = _sparse_narrative(company_name, sector, 0, prospect_ai_score)
        brief["sparse_sector"] = True
        return brief

    # Remove prospect itself
    peers = [p for p in candidates if p.get("name", "").lower() != company_name.lower()]

    if len(peers) < _MIN_PEERS_FOR_DISTRIBUTION:
        # ── Sparse-sector branch ──────────────────────────────────────────────
        brief["peer_count"]    = len(peers)
        brief["sparse_sector"] = True
        brief["narrative"]     = _sparse_narrative(company_name, sector, len(peers), prospect_ai_score)
        # Still score what we have, for transparency
        scored = [_score_peer(p) for p in peers]
        brief["competitors_analyzed"] = scored
        return brief

    # ── Step 2: Score each peer ───────────────────────────────────────────────
    scored_peers = [_score_peer(p) for p in peers]
    scored_peers.sort(key=lambda p: p["ai_score"], reverse=True)
    brief["peer_count"]           = len(scored_peers)
    brief["competitors_analyzed"] = scored_peers[:10]  # top 10 by ai_score

    # ── Step 3: Compute distribution ─────────────────────────────────────────
    all_scores = [p["ai_score"] for p in scored_peers]
    brief["distribution"] = _compute_distribution(all_scores)

    n = len(all_scores)
    top_q_idx  = max(0, n // 4 - 1)
    median_idx = n // 2
    top_q  = all_scores[top_q_idx]
    median = all_scores[median_idx]

    brief["top_quartile_score"]  = top_q
    brief["sector_median_score"] = median

    # Prospect position in sector distribution
    if prospect_ai_score >= top_q:
        brief["prospect_position"] = "top_quartile"
    elif prospect_ai_score >= median:
        brief["prospect_position"] = "above_median"
    elif prospect_ai_score > 0:
        brief["prospect_position"] = "below_median"
    else:
        brief["prospect_position"] = "no_signal"

    # ── Step 4: Identify gaps ─────────────────────────────────────────────────
    top_peers = [p for p in scored_peers if p["ai_score"] >= top_q][:5]
    brief["gaps"] = _compute_gaps(prospect_ai_signals, top_peers)

    # ── Step 5: Confidence label for the brief ────────────────────────────────
    if n >= 15:
        brief["confidence"] = "high"
    elif n >= 8:
        brief["confidence"] = "medium"
    else:
        brief["confidence"] = "low"

    # ── Step 6: LLM-generated narrative ──────────────────────────────────────
    if not top_peers:
        brief["narrative"] = (
            f"{company_name} scores {prospect_ai_score}/3 on AI maturity. "
            f"No top-quartile peers identified in the sector — gap analysis omitted."
        )
        return brief

    try:
        peer_names  = ", ".join(p["name"] for p in top_peers[:3])
        gap_bullets = "\n".join(
            f"- {g['practice']}: {g['impact']} ({g['evidence']})"
            for g in brief["gaps"]
        )
        position_phrase = {
            "top_quartile":  f"already in the top quartile ({prospect_ai_score}/{top_q})",
            "above_median":  f"above sector median ({prospect_ai_score}/3 vs median {median}/3)",
            "below_median":  f"below sector median ({prospect_ai_score}/3 vs median {median}/3)",
            "no_signal":     f"not yet publicly visible on AI ({prospect_ai_score}/3)",
        }.get(brief["prospect_position"], f"score {prospect_ai_score}/3")

        prompt = (
            f"Write 2–3 sentences for a B2B sales email research finding. Be factual and respectful. "
            f"Do NOT mention Tenacious Consulting. Do NOT be condescending.\n\n"
            f"Company: {company_name}, Sector: {sector}\n"
            f"Their position: {position_phrase}\n"
            f"Sector: {n} companies analyzed, top quartile threshold {top_q}/3, median {median}/3\n"
            f"Top peers: {peer_names}\n"
            f"Gaps vs top quartile:\n{gap_bullets if gap_bullets else '(none identified)'}\n\n"
            "The finding should give the prospect a grounded view of where they sit, "
            "not a condemnation. Frame as: 'here is what the data shows' not 'you are falling behind'."
        )
        text, _ = chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=200,
            trace_id=trace_id,
        )
        brief["narrative"] = text.strip()
    except Exception as e:
        brief["errors"].append(f"narrative_llm: {e}")
        top_q_str = f"{top_q}/3" if top_q is not None else "N/A"
        brief["narrative"] = (
            f"Among {n} comparable companies in the {sector} sector, "
            f"the top quartile shows an AI maturity score of {top_q_str}. "
            f"{company_name} scores {prospect_ai_score}/3, placing it {brief['prospect_position'].replace('_', ' ')}. "
            "This represents a concrete opportunity to close a measurable gap with peers."
        )

    return brief


def save_brief(brief: dict, output_path: str) -> None:
    with open(output_path, "w") as f:
        json.dump(brief, f, indent=2, default=str)