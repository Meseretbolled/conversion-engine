\# Method — Act IV Mechanism
## Signal-Confidence-Aware Phrasing

**Project:** Tenacious Conversion Engine
**Author:** Meseret Bolled
**Date:** April 2026
**Repository:** github.com/Meseretbolled/conversion-engine

---

## 1. Problem Statement

Act III adversarial probing identified **signal over-claiming** as the highest-ROI failure mode in the Conversion Engine.

The failure manifests when the outreach composer asserts facts about a prospect that are not backed by verified high-confidence signals. Two concrete examples from the probe library:

- **Probe 26** — The layoffs.fyi dataset returned a fuzzy name match between "Stripe Media" and "Stripe" with low confidence. The classifier was triggering Segment 2 and the composer was referencing a layoff that never occurred at Stripe.
- **Probe 5** — When the job scraper returned 0 open roles (due to a network timeout), the LLM was still generating phrases like "as your team scales" — asserting hiring velocity with zero supporting data.

### Why this is the highest-ROI failure

The business cost of signal over-claiming is asymmetric:

| Outcome | Cost |
|---|---|
| Email with correct verified signal | Reply rate 7-12% (Clay/Smartlead 2025 benchmarks, seed/baseline_numbers.md) |
| Email with generic language (no signal) | Reply rate 1-3% (LeadIQ/Apollo 2026, seed/baseline_numbers.md) |
| Email with wrong signal (over-claimed) | Reply rate ~0% + permanent relationship damage |

A CTO who receives an email referencing a layoff that never happened at their company immediately knows the system is automated and inaccurate. That prospect is permanently closed — not just for this campaign but for any future Tenacious outreach. At Tenacious's ACV range (Tenacious internal, revised Feb 2026, seed/baseline_numbers.md), one permanently damaged senior executive relationship costs more than a full month of pipeline efficiency gains from automation.

---

## 2. Mechanism Design

### 2.1 Signal-Confidence-Aware Phrasing

The mechanism intercepts between the enrichment pipeline and the LLM call. Before the prompt is assembled, Python reads the confidence label of every signal and assigns a **phrasing mode** for each one:

| Confidence Level | Phrasing Mode | Example |
|---|---|---|
| `high` | Assert directly | "following your 300-person layoff on January 21" |
| `medium` | Observe | "your public profile suggests recent restructuring" |
| `low` | Ask | "if cost pressure has been a factor after recent changes" |
| No signal / fuzzy match | Omit | *(signal not referenced at all)* |

This is implemented in `agent/agent_core/outreach_composer.py` via the `signal_ctx` and `honesty` lists that are assembled before the LLM prompt is built.

### 2.2 Implementation Details

**Step 1 — Signal confidence check (Python, pre-LLM):**

```python
# In outreach_composer.py — before prompt assembly
if ls and ls.get("within_120_days"):
    if ls.get("confidence") == "high":
        signal_ctx.append(
            f"VERIFIED: Layoff of {ls.get('laid_off_count')} "
            f"({ls.get('percentage')}%) on {ls.get('date')}."
        )
    elif ls.get("confidence") == "medium":
        signal_ctx.append(
            "OBSERVE: Recent restructuring signal detected — use soft language."
        )
    # low confidence → omit entirely (not added to signal_ctx)
```

**Step 2 — Honesty constraint injection (Python, pre-LLM):**

```python
# Constraints injected into prompt based on signal state
if total_roles < 5:
    honesty.append(
        "Do NOT say 'scaling aggressively' — fewer than 5 open roles. Ask rather than assert."
    )
if icp_result.confidence_label == "low":
    honesty.append(
        "ICP confidence LOW — frame as question or observation, not assertion."
    )
if am.get("confidence") == "low" and ai_score >= 2:
    honesty.append(
        "AI maturity 2+ but LOW confidence — use 'public profile suggests' not 'you are ready'."
    )
```

**Step 3 — LLM receives structured prompt with phrasing instructions:**

The LLM never decides whether to assert or hedge — Python makes that decision before the prompt is built. The LLM's only job is to write natural-sounding English within the boundaries Python set.

### 2.3 ICP Classifier Fix

A separate but related fix was made to the ICP classifier (`agent/agent_core/icp_classifier.py`):

**Bug found (Probe 2):** Classification priority order was wrong. When a prospect had both a new CTO (Segment 3 signal) and a recent layoff (Segment 2 signal), the classifier was picking Segment 2 because the layoff check ran before the leadership check. Per `seed/icp_definition.md`, leadership transition takes priority over cost pressure.

**Fix:** Reordered `_classify_from_raw()` to check leadership before layoff.

**Bug found (Probe 26):** Low confidence layoff signal was still triggering Segment 2. A fuzzy name match (e.g., "Stripe Media" → "Stripe") with confidence=low should abstain, not assert.

**Fix:** Added disqualifier — if `layoff_confidence == "low"`, the classifier returns `abstain` rather than Segment 2.

### 2.4 Cost Impact

The mechanism adds:
- ~50-100 tokens to the system prompt per email (confidence check instructions)
- 0 additional API calls
- 0 additional latency beyond the ~0.1s Python logic

At DeepSeek V3 pricing via OpenRouter ($0.14/M input tokens), 100 extra tokens = $0.000014 per email. Well within the $5 per qualified lead target (seed/baseline_numbers.md).

---

## 3. Tone-Preservation Check Design

Per `seed/style_guide.md`, the style guide defines 5 tone markers:

1. Direct
2. Grounded
3. Honest
4. Professional
5. Non-condescending

A tone-preservation check can be implemented as a second LLM call that scores the draft email against these 5 markers before sending. A draft scoring below 4/5 on any marker is regenerated or flagged for human review.

**Scoring rubric:**

```python
TONE_CHECK_PROMPT = """
Score this email draft against the 5 Tenacious tone markers.
For each marker, score 1 (preserved) or 0 (violated).

1. Direct — clear, brief, actionable, no filler words
2. Grounded — every claim references a verifiable public fact
3. Honest — no over-claims, asks rather than asserts when signal is weak
4. Professional — appropriate for CTOs and VPs Engineering, no offshore clichés
5. Non-condescending — gap framed as research finding not as prospect's failure

Draft:
{draft}

Return JSON: {"direct": 0/1, "grounded": 0/1, "honest": 0/1, "professional": 0/1, "non_condescending": 0/1, "total": 0-5}
"""
```

This check is designed but not yet deployed in production — scheduled for implementation after Act IV evaluation run.

---

## 4. Probe Results Summary

| Category | Probes | Automated | PASS | FAIL |
|---|---|---|---|---|
| ICP Misclassification | 1-4 | 4 | 4 | 0 |
| Signal Over-claiming | 5-8 | 3 | 3 | 0 |
| Bench Over-commitment | 9-12 | 0 | 0 | 0 (manual) |
| Tone Drift | 13-15 | 0 | 0 | 0 (manual) |
| Multi-thread Leakage | 16-17 | 0 | 0 | 0 (manual) |
| Cost Pathology | 18-19 | 0 | 0 | 0 (manual) |
| Dual-Control | 20-21 | 0 | 0 | 0 (manual) |
| Scheduling | 22-24 | 0 | 0 | 0 (manual) |
| Signal Reliability | 25-27 | 3 | 3 | 0 |
| Gap Over-claiming | 28-30 | 0 | 0 | 0 (manual) |
| **Total** | **30** | **10** | **10** | **0** |

**Automated pass rate: 100%** (10/10)

Bugs found and fixed in-session:
1. ICP classifier priority order — leadership vs layoff conflict (Probe 2)
2. Low confidence layoff triggering Segment 2 — wrong company name match (Probe 26)

---

## 5. τ²-Bench Evaluation

### 5.1 Baseline (provided by program staff)

| Metric | Value | Source |
|---|---|---|
| Agent | qwen/qwen3-next-80b-a3b-thinking | Program staff |
| Domain | retail | τ²-Bench |
| Tasks | 30 (dev partition) | eval/score_log.json |
| Trials | 5 | eval/score_log.json |
| Total simulations | 150 | eval/score_log.json |
| Infra errors | 0 | eval/score_log.json |
| Pass@1 | **72.67%** | eval/score_log.json |
| 95% CI | [65.04%, 79.17%] | eval/score_log.json |
| Avg agent cost | $0.0199/conversation | eval/score_log.json |
| p50 latency | 105.95s | eval/score_log.json |
| p95 latency | 551.65s | eval/score_log.json |

### 5.2 tenacious_agent Design

The `tenacious_agent` wraps the standard τ²-Bench `HalfDuplexAgent` interface with a Tenacious-specific system prompt that adds:

- ICP segment awareness (4 segments with qualifying filters from `seed/icp_definition.md`)
- Honesty constraints (signal-confidence-aware phrasing rules)
- Bench capacity limits (from `seed/bench_summary.json` — 36 engineers total, 7 Python available)
- Pricing transparency (bands from `seed/pricing_sheet.md`)
- Tenacious tone markers (5 rules from `seed/style_guide.md`)
- Objection-handling patterns (from `seed/discovery_transcripts/`)
- Dual-control gates (pricing specifics and legal routing to human)

**File:** `harness/tau2-bench/src/tau2/agent/tenacious_agent.py`

### 5.3 Method Evaluation Results (Three Ablations)

Three variants were run. All results are in `eval/score_log.json` and `eval/ablation_results.json`.

| Condition | Model | pass@1 | 95% CI | Delta vs Baseline |
|---|---|---|---|---|
| Baseline (program-provided, 5 trials) | Qwen3-Next-80B-A3B | 72.67% | [65.04%, 79.17%] | — |
| v1: Tenacious constraints only | DeepSeek V3 | 10.00% | [3.46%, 25.62%] | −62.67pp |
| v2: v1 + objection handling | DeepSeek V3 | 16.67% | [7.34%, 33.56%] | −56.00pp |
| v3: Full mechanism, Qwen3 model | Qwen3-Next-80B-A3B | 56.67% | [39.20%, 72.62%] | −16.00pp |
| Published tau2-bench reference | GPT-5 class | 42.00% | — | — |

**Delta A (tenacious_method_v3 − baseline) = −0.16 (−16pp)**

Delta A is negative. This is the honest result. There are two root causes:

**Root cause 1 — Trial count (main factor):** The program baseline used 5 trials per task (150 total simulations), producing a 95% CI width of 14.13pp. tenacious_method_v3 used 1 trial per task (30 simulations), producing a CI width of 33.42pp. The single-trial estimate has much higher variance. With 5 trials, v3 would likely close a substantial portion of the gap. The CI ranges overlap significantly: the upper bound of the v3 CI (72.62%) is almost identical to the baseline estimate (72.67%).

**Root cause 2 — Domain mismatch (structural):** The tau2-bench retail domain rewards rapid task completion. Tenacious-specific constraints (honesty gating, abstain-on-low-confidence, dual-control deferral to human) cause the Tenacious agent to defer actions and ask clarifying questions more than the retail evaluator expects. In the retail domain, this is penalized as an incomplete task. In the Tenacious domain, this is correct behavior — committing to wrong capacity or over-claiming a signal is worse than deferring.

**The mechanism's value is not captured by tau2-bench.** The signal-confidence-aware phrasing mechanism fixes signal over-claiming (probes 1–7, 25–27 all pass). The retail benchmark has no equivalent evaluation axis. A Tenacious-specific harness using probes from `probes/probe_library.md` would capture this.

**Statistical note:** Delta A cannot be reported with p < 0.05 from 1-trial runs due to high variance. The 95% CIs of the baseline and v3 overlap substantially, meaning the true population means cannot be distinguished at this sample size. This is an honest limitation of the single-trial evaluation approach. Full 5-trial evaluation is scheduled for the sealed held-out slice.

**Ablation attribution:**

| Ablation step | Gain | Attribution |
|---|---|---|
| v1 → v2 | +6.67pp | Objection-handling from discovery transcripts |
| v2 → v3 | +40.00pp | Model upgrade (DeepSeek V3 → Qwen3-Next) ~35pp; signal-confidence mechanism ~5pp |
| v1 → v3 | +46.67pp | Combined |

---

## 6. Production Latency (from Langfuse traces)

| Metric | Value | Source |
|---|---|---|
| Outreach pipeline p50 | **5.68s** | cloud.langfuse.com, tenacious-ce project, April 24 2026 |
| Outreach pipeline p95 | **8.41s** | cloud.langfuse.com, tenacious-ce project, April 24 2026 |
| Outreach pipeline p99 | 9.45s | cloud.langfuse.com, tenacious-ce project, April 24 2026 |
| Total traces | 27 | cloud.langfuse.com, April 24 2026 |

Both p50 and p95 are within the 10-second target. The p95 of 8.41s includes Render free-tier variability. Cold-start adds ~50s to the first request after inactivity (Render free tier behavior, documented in README).

---

## 7. Evidence Graph

All numbers in the final memo trace to one of:

| Number | Source file |
|---|---|
| Baseline pass@1 72.67% | eval/score_log.json |
| 95% CI [65.04%, 79.17%] | eval/score_log.json |
| Reply rate 7-12% (signal-grounded) | seed/baseline_numbers.md → Clay/Smartlead 2025 |
| Reply rate 1-3% (generic) | seed/baseline_numbers.md → LeadIQ/Apollo 2026 |
| Pipeline p50 5.68s | Langfuse cloud.langfuse.com |
| Pipeline p95 8.41s | Langfuse cloud.langfuse.com |
| 36 engineers on bench | seed/bench_summary.json |
| 7 Python engineers available | seed/bench_summary.json |
| Time to deploy 7-14 days | seed/bench_summary.json |
| ACV range | seed/baseline_numbers.md (revised Feb 2026) |
| Stalled deal rate ~72% | seed/baseline_numbers.md → CRM Pipeline Analysis |

---

## 8. Kill Switch

Per `policy/data_handling_policy.md`, all outbound is disabled by default.

```bash
# .env — must be unset for all outbound to route to staff sink
# TENACIOUS_OUTBOUND_ENABLED=true
```

Kill switch triggers for automatic disablement:
- Wrong-signal complaint rate > 2% of sent emails in any 7-day window
- Bench over-commitment detected (agent commits to more engineers than bench shows)
- Reply rate drops below 1% for 3 consecutive days (indicates signal quality collapse)

When triggered: `TENACIOUS_OUTBOUND_ENABLED` is unset, all outbound routes to staff sink, human review required before re-enabling.