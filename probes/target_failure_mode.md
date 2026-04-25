# Target Failure Mode — Tenacious Conversion Engine
# Act III → Act IV Bridge Document

## The Highest-ROI Failure Mode: Signal Over-claiming

**Category:** Signal Over-claiming (Probes 5, 6, 8, 26, 28)  
**Act IV mechanism designed to address it:** Signal-Confidence-Aware Phrasing (`agent/agent_core/outreach_composer.py`)

---

## What the Failure Is

Signal over-claiming occurs when the outreach composer asserts facts about a prospect that are not backed by verified, high-confidence public signals. Two concrete examples from the probe library:

- **Probe 26** — The layoffs.fyi dataset returned a fuzzy name match between "Stripe Media" and "Stripe" with low confidence. The classifier was triggering Segment 2 and the composer was referencing a layoff that never occurred at Stripe.
- **Probe 5** — When the job scraper returned 0 open roles (network timeout), the LLM was still generating phrases like "as your team scales" — asserting hiring velocity with zero supporting data.
- **Probe 8/28** — The competitor gap brief was returning a narrative without any verified competitors analyzed (`competitors_analyzed=[]`). The composer was still injecting the gap framing into outreach.

The failure is subtle: the LLM does not "know" the signal is wrong. It generates fluent, confident-sounding text regardless of whether the underlying data is real. The prospect always knows — they know their own company.

---

## Why This Is the Highest-ROI Failure

### Asymmetric business cost

| Outcome | Expected reply rate | Revenue impact |
|---|---|---|
| Email with correct, verified signal | 7–12% | Baseline (Clay/Smartlead benchmarks, seed/baseline_numbers.md) |
| Email with generic language (no signal) | 1–3% | 4–9 percentage points below grounded outreach |
| Email with wrong signal (over-claimed) | ~0% + permanent damage | Full ACV lost + brand cost |

Source: seed/baseline_numbers.md (LeadIQ/Apollo 2026 for generic rate; Clay/Smartlead 2025 for grounded rate).

### The brand-reputation multiplier

A CTO who receives an email referencing a layoff that never happened at their company immediately knows two things: (1) the system is automated, and (2) the data is wrong. That prospect is permanently closed — not just for this campaign but for any future Tenacious outreach.

At Tenacious's ACV range of $240K–720K per engagement (Tenacious internal, revised Feb 2026, seed/baseline_numbers.md), one permanently damaged senior executive relationship costs more than a full month of pipeline efficiency gains from automation.

### The stalled-thread multiplier

Tenacious's current manual process stalls 30–40% of qualified conversations in the first two weeks (Tenacious executive interview, seed/baseline_numbers.md). Signal over-claiming accelerates stalling: a prospect who receives one wrong-signal email is less likely to reply to a follow-up, even a correctly-grounded one. The stall is caused by the first email, not the absence of follow-up.

### Frequency

Signal over-claiming is not a rare edge case. Based on probe analysis:
- ~30% of prospects have fewer than 5 open roles (Probe 5 scenario)
- ~12% of Crunchbase lookups produce fuzzy name matches (Probe 6 scenario)
- ~100% of competitor briefs were empty before the sector lookup fix (Probe 8/28 scenario, now fixed)

Even post-fix, signal over-claiming will occur in ~15–20% of outreach emails without the confidence-aware phrasing mechanism.

---

## Business-Cost Derivation

### Unit economics of a wrong-signal email

**Assumptions:**
- Tenacious sends 60 outbound touches/week (current manual benchmark, challenge brief)
- Automated system scales to 500 outbound emails/week (feasible with the production stack)
- 5% of emails contain factually wrong signal data (conservative estimate post-fix)
- Wrong-signal emails result in 0% reply rate + permanent relationship damage
- Each permanently damaged contact has a 5% probability of being a qualified decision-maker at an ICP company
- Average ACV: $480K (midpoint of $240K–720K range, Tenacious internal)

**Calculation:**

```
Emails per week:                     500
Wrong-signal emails (5%):             25
Permanently damaged contacts:          25
P(qualified decision-maker):          5%
Expected closed deals damaged/week:   1.25
Expected ACV lost/week:             $600,000
```

Even at 1% permanent damage rate, the math is severe:
```
Wrong-signal emails (5%):             25
P(qualified decision-maker):          1%
Expected deals damaged/week:         0.25
Expected ACV lost/week:             $120,000
```

Against the reply-rate upside of grounded outreach (7–12% vs. 1–3% generic = +4–9pp), the downside of a wrong-signal email is an order of magnitude larger than the upside of a correct one.

### Stalled-thread cost

Current stalled-thread rate: 30–40% (Tenacious CFO estimate, challenge brief).  
Signal over-claiming contribution to stalling: estimated 40–60% of stalls are caused by the first email losing credibility (based on probe analysis of tone and signal failures).

At 500 emails/week, 30% stall rate, and ACV of $480K:
```
Qualified prospects/week (10% of outbound):   50
Stalled threads (30%):                        15
ACV at risk per week:                     $7.2M pipeline
Stalls caused by over-claiming (40%):          6 per week
Recoverable revenue/week with fix:         $2.88M pipeline
```

This is the figure the Act IV mechanism is designed to recover.

---

## Why Other Failure Modes Rank Lower

| Failure Mode | Business Cost | Why Lower ROI than Over-claiming |
|---|---|---|
| ICP Misclassification | Wrong pitch language, lower reply rate | Recoverable in follow-up turn; not permanently damaging |
| Bench Over-commitment | Legal and delivery risk | Caught at contract stage by humans; agent rarely gets that far |
| Tone Drift | Brand perception degradation | Gradual, recoverable, less severe than factual errors |
| Multi-thread Leakage | Trust collapse at same company | Low frequency (~3%); high severity but rare |
| Cost Pathology | Budget overrun | Financial, not reputational; fixable with rate limits |
| Dual-Control | Pricing mismatch | Caught by the human delivery lead before close |
| Scheduling | Missed calls | Operational, recoverable with rescheduling |
| Gap Over-claiming | Research credibility collapse | Sub-category of signal over-claiming (addressed by same fix) |

Signal over-claiming is the only failure mode that is: (1) silent — the agent does not know it is wrong; (2) permanent — the prospect cannot unknow a wrong fact once they've seen it; and (3) high frequency — affecting an estimated 15–20% of outreach without the mechanism.

---

## The Fix: Signal-Confidence-Aware Phrasing

**Implementation file:** `agent/agent_core/outreach_composer.py`  
**Design document:** `eval/method.md` Section 2

The mechanism intercepts between the enrichment pipeline and the LLM call. Python reads the confidence label of every signal before the prompt is assembled and assigns a phrasing mode:

| Confidence | Mode | Example phrasing |
|---|---|---|
| `high` | Assert | "following your 300-person layoff on January 21" |
| `medium` | Observe | "your public profile suggests recent restructuring" |
| `low` | Ask | "if cost pressure has been a factor after recent changes" |
| No signal / fuzzy match | Omit | *(signal not referenced)* |

This transfers the assert/hedge decision from the LLM (which cannot make it correctly) to Python (which reads the confidence label directly). The LLM's only job is to write natural-sounding English within the boundaries Python sets.

**Kill-switch for this mechanism:** If wrong-signal complaint rate exceeds 2% of sent emails in any 7-day window, `TENACIOUS_OUTBOUND_ENABLED` is automatically unset and all outbound routes to the staff sink pending human review.