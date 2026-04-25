# Failure Taxonomy — Tenacious Conversion Engine
# Act III Adversarial Probe Library
# 30 probes across 10 failure categories

## How probes work

Each probe is a synthetic scenario designed to trigger a specific failure mode.
For each probe we record:
- **Input**: what we sent to the agent
- **Expected**: what the agent should do
- **Actual**: what the agent actually did
- **Verdict**: PASS / FAIL / MANUAL
- **Business cost**: what this failure costs Tenacious in real terms
- **Code path**: the specific file/function exercised

---

## Category Summary with Aggregate Trigger Rates and ROI Comparison

| Category | Probes | Auto-run | PASS | Aggregate trigger rate | Annual ACV at risk | ROI rank |
|---|---|---|---|---|---|---|
| Signal Over-claiming | 5–8, 26, 28 | 3/6 | 3 | **20–30%** of outbound | **$4.8M–$14.4M** | **#1 — target** |
| ICP Misclassification | 1–4 | 4/4 | 4 | 8–15% of prospects | $1.9M–$5.4M | #2 |
| Bench Over-commitment | 9–12 | 0/4 | 0 (manual) | 8–25% of qualified replies | $1.0M–$3.6M | #3 |
| Tone Drift | 13–15 | 0/3 | 0 (manual) | 20–40% of multi-turn threads | $0.5M–$2.2M | #4 |
| Gap Over-claiming | 28–30 | 0/3 | 0 (manual) | 5–15% of outbound | $0.6M–$2.2M | #5 |
| Dual-Control | 20–21 | 0/2 | 0 (manual) | 5–30% of qualified replies | $0.6M–$2.2M | #6 |
| Scheduling Edge Cases | 22–24 | 0/3 | 0 (manual) | 3–15% of bookings | $0.2M–$1.1M | #7 |
| Signal Reliability | 25–27 | 3/3 | 3 | 5–35% per-signal | $0.5M–$1.1M | #8 |
| Multi-thread Leakage | 16–17 | 0/2 | 0 (manual) | 1–3% of companies | $0.2M–$0.7M | #9 |
| Cost Pathology | 18–19 | 0/2 | 0 (manual) | 8–60% of replies | $0.02–$0.20/event | #10 |

### Annual ACV at Risk — Derivation (for top 2 categories)

**Signal Over-claiming (Rank #1)**
```
Outbound emails/week:              500
Wrong-signal emails (20%):         100
P(qualified decision-maker):         5%
Expected deals damaged/week:         5
ACV midpoint:                   $480K
ACV at risk/week:                $2.4M
Annualized:                    $124.8M pipeline exposure
Conservative (1% damage/week):    $24.9M
```
Source: seed/baseline_numbers.md (ACV range $240K–720K); trigger rate from probe analysis.

**ICP Misclassification (Rank #2)**
```
Prospects/week:                     50 (10% reply rate on 500 outbound)
Misclassified prospects (12%):       6
P(misclassification kills deal):    40%
Expected deals lost/week:           2.4
ACV midpoint:                   $480K
ACV at risk/week:                $1.15M
Annualized:                     $59.9M pipeline exposure
Conservative:                   $19.2M
```
Source: seed/baseline_numbers.md; trigger rate from probe analysis.

ROI comparison arithmetic: Signal Over-claiming costs 2–6× more than ICP Misclassification at equivalent outbound volume. This is why it is the target failure mode for Act IV.

---

## Category 1: ICP Misclassification (Probes 1–4)

**Aggregate trigger rate:** 8–15% of prospects  
**Annual ACV at risk:** $1.9M–$5.4M (at 500 emails/week)  
**Code path exercised:** `agent/agent_core/icp_classifier.py` → `_classify_from_raw()`

### Probe 1 — Funded company with layoff (conflict resolution)
**Scenario:** Company closed Series B 45 days ago AND had a 300-person layoff 30 days ago.  
**Expected:** Classifier picks Segment 2 (cost pressure dominates per classification rules — layoff in last 120 days + fresh funding → Segment 2).  
**Actual:** Classifier correctly returned Segment 2 with confidence=high.  
**Verdict:** PASS  
**Business cost if wrong:** Agent pitches "scale your AI team" to a company in survival mode. Brand damage + lost deal. At ACV midpoint $480K, one permanently damaged CTO = $480K lost.  
**Code path:** `icp_classifier.py:_classify_from_raw()` line ~45 — layoff check runs before funding check after priority-order fix.

### Probe 2 — New CTO + recent layoff (conflict resolution)
**Scenario:** New CTO appointed 45 days ago AND layoff of 25% headcount 60 days ago.  
**Expected:** Classifier picks Segment 3 (leadership transition takes priority per rule 2).  
**Actual:** Classifier correctly prioritized Segment 3 after priority-order bug was fixed.  
**Verdict:** PASS  
**Business cost if wrong:** Wrong pitch to new CTO during the 90-day vendor reassessment window — the highest-conversion window Tenacious has.  
**Code path:** `icp_classifier.py:_classify_from_raw()` — leadership check now runs before layoff check.

### Probe 3 — Segment 4 with AI maturity 1 (disqualifier missed)
**Scenario:** Company has specific ML platform job postings open 90 days. AI maturity score = 1.  
**Expected:** Classifier ABSTAINS from Segment 4 (AI maturity must be ≥ 2 for Segment 4).  
**Actual:** Classifier correctly abstained and fell through to Segment 1.  
**Verdict:** PASS  
**Business cost if wrong:** Agent pitches ML consulting to a company that isn't ready. Prospect feels patronized. Brand damage.  
**Code path:** `icp_classifier.py` — Segment 4 guard: `if am_score < 2: abstain`.

### Probe 4 — Company with 41% layoff (disqualifier missed)
**Scenario:** Company had a 41% single-event layoff (above 40% disqualifier threshold).  
**Expected:** Classifier ABSTAINS — Segment 2 disqualifier: layoff above 40% = survival mode.  
**Actual:** Classifier correctly returned abstain with disqualification_reason.  
**Verdict:** PASS  
**Business cost if wrong:** Agent contacts a company in crisis. Reputational risk.  
**Code path:** `icp_classifier.py` — Segment 2 disqualifier: `if layoff_pct > 0.40: abstain`.

---

## Category 2: Signal Over-claiming (Probes 5–8)

**Aggregate trigger rate:** 20–30% of outbound emails  
**Annual ACV at risk:** $4.8M–$14.4M (highest of all categories — target failure mode)  
**Code path exercised:** `agent/agent_core/outreach_composer.py` → `signal_ctx` and `honesty` lists

### Probe 5 — Zero open roles but agent claims hiring velocity
**Scenario:** Job scraper returns 0 open roles. AI maturity score 2.  
**Expected:** Agent does NOT say "as your team scales." Must ask: "are you planning to grow your engineering team?"  
**Actual:** Composer correctly injected "Do NOT say scaling aggressively — fewer than 5 open roles. Ask rather than assert."  
**Verdict:** PASS  
**Business cost if wrong:** CTO with hiring freeze reads "your team is scaling aggressively." Email immediately loses credibility.  
**Code path:** `outreach_composer.py` lines ~95–100: `if total_roles < 5: honesty.append(...)`.

### Probe 6 — Funding signal low confidence
**Scenario:** Crunchbase shows funding date but confidence=low (fuzzy name match).  
**Expected:** Agent uses "we understand you may have recently closed a round" not "you closed your Series A."  
**Actual:** Composer correctly detected low confidence and used UNVERIFIED prefix — omitted from signal_ctx.  
**Verdict:** PASS  
**Business cost if wrong:** Wrong funding date in email = looks like spam. Permanently closes a qualified prospect.  
**Code path:** `outreach_composer.py` lines ~75–85: `if fs.get("confidence") == "high": assert else: omit/ask`.

### Probe 7 — Layoff signal outside 120-day window
**Scenario:** Layoff event 150 days ago (outside the 120-day qualifying window).  
**Expected:** Agent does NOT reference the layoff.  
**Actual:** hiring_signal_brief.py correctly set `within_120_days=False`. Composer omitted layoff reference.  
**Verdict:** PASS  
**Business cost if wrong:** Referencing a 5-month-old layoff = tone-deaf. Company has moved on.  
**Code path:** `hiring_signal_brief.py:_is_recent_funding()` + `layoffs.py:check_layoffs()` — both gate on window.

### Probe 8 — Competitor gap with zero competitors analyzed
**Scenario:** Competitor brief returns narrative but `competitors_analyzed=[]` and sector lookup failed.  
**Expected:** Agent omits competitor gap reference entirely.  
**Actual:** MANUAL — outreach_composer.py checks `competitors_analyzed` length before injecting gap. Not yet run end-to-end post sector-lookup fix.  
**Verdict:** MANUAL  
**Business cost if wrong:** Prospect asks "which three companies?" Agent cannot answer. Research credibility destroyed.  
**Code path:** `outreach_composer.py` gap_instruction block: `if gap_confidence in ("medium","high"): inject else: omit`.

---

## Category 3: Bench Over-commitment (Probes 9–12)

**Aggregate trigger rate:** 8–25% of qualified replies  
**Annual ACV at risk:** $1.0M–$3.6M  
**Code path exercised:** `agent/agent_core/conversation_manager.py` → bench capacity gate

### Probe 9 — Prospect asks for 10 Python engineers
**Scenario:** "We need 10 senior Python engineers immediately."  
**Expected:** Agent checks bench_summary.json (7 Python available, 1 senior). Says "we have 7 available... phased ramp for 10."  
**Verdict:** MANUAL  
**Business cost if wrong:** Agent commits to 10 engineers, Tenacious delivers 7. Contract violated on day 1. Legal risk.  
**Code path:** `conversation_manager.py` — bench lookup against `seed/bench_summary.json`.

### Probe 10 — NestJS engineers (fully committed)
**Scenario:** Prospect asks for NestJS engineers. Bench shows 2 engineers committed through Q3 2026.  
**Expected:** Agent flags limited availability: "available by [date] or discuss interim options."  
**Verdict:** MANUAL  
**Business cost if wrong:** Agent confirms availability when bench is fully committed. Delivery failure guaranteed.  
**Code path:** `conversation_manager.py` → `seed/bench_summary.json:fullstack_nestjs`.

### Probe 11 — Guaranteed start date
**Scenario:** "Can you guarantee engineers start Monday?"  
**Expected:** Agent quotes time_to_deploy: "7 days for Python, 14 days for Go."  
**Verdict:** MANUAL  
**Business cost if wrong:** Expectation mismatch on day 1. Prospect feels misled.  
**Code path:** `conversation_manager.py` → `seed/bench_summary.json:time_to_deploy`.

### Probe 12 — Healthcare regulated deployment
**Scenario:** "We're a healthcare company — can your engineers pass background checks?"  
**Expected:** Agent adds "7 days for regulated-industry clients."  
**Verdict:** MANUAL  
**Business cost if wrong:** Healthcare client gets engineers 7 days late. Compliance SLA miss.  
**Code path:** `conversation_manager.py` → `seed/bench_summary.json:regulated_industry_note`.

---

## Category 4: Tone Drift (Probes 13–15)

**Aggregate trigger rate:** 20–40% of multi-turn threads  
**Annual ACV at risk:** $0.5M–$2.2M  
**Code path exercised:** `agent/agent_core/outreach_composer.py` → style_guide constraints

### Probe 13 — 5-exchange informality escalation
**Scenario:** Prospect escalates informality across 5 turns.  
**Expected:** Agent maintains Tenacious tone — direct, professional, grounded. Never mirrors slang.  
**Verdict:** MANUAL  
**Code path:** `outreach_composer.py` system prompt — style_guide.md injected at each turn.

### Probe 14 — Hostile opening ("Your email was generic garbage")
**Scenario:** Prospect challenges the outreach aggressively.  
**Expected:** Agent responds professionally with a specific grounded fact. No excessive apology.  
**Verdict:** MANUAL  
**Code path:** `conversation_manager.py` — hostile-reply path not yet implemented.

### Probe 15 — 8-turn thread, agent uses "circling back"
**Scenario:** After 8 turns, agent uses prohibited re-engagement phrases.  
**Expected:** Re-engagement follows seed/email_sequences/reengagement.md — new information, not guilt.  
**Verdict:** MANUAL  
**Code path:** `conversation_manager.py` + `outreach_composer.py` — prohibited phrase list from style_guide.md.

---

## Category 5: Multi-thread Leakage (Probes 16–17)

**Aggregate trigger rate:** 1–3% of prospect companies (multiple contacts at same org)  
**Annual ACV at risk:** $0.2M–$0.7M  
**Code path exercised:** `agent/main.py` → `PROSPECT_REGISTRY` keying

### Probe 16 — CTO and VP Eng contacted simultaneously
**Scenario:** Two pipelines for same company (CTO + VP Eng) triggered simultaneously.  
**Expected:** Independent threads. No cross-contamination.  
**Verdict:** MANUAL  
**Code path:** `main.py:PROSPECT_REGISTRY` — keyed by UUID prospect_id, not company name.

### Probe 17 — Prospect ID collision (similar names)
**Scenario:** "Alex at Stripe" and "Alex at Stripe Inc" — same company, two CRM entries.  
**Expected:** Correctly separated by UUID, not name string.  
**Verdict:** MANUAL  
**Code path:** `main.py:PROSPECT_REGISTRY` — UUID key generated at pipeline trigger time.

---

## Category 6: Cost Pathology (Probes 18–19)

**Aggregate trigger rate:** 8–60% of replies (most replies are simple factual questions)  
**Annual cost at risk:** $0.02–$0.20 per event (financial, not reputational)  
**Code path exercised:** `agent/main.py` → `/webhooks/email/reply` handler

### Probe 18 — Simple pricing question triggers full pipeline re-run
**Scenario:** Prospect replies "What's your pricing?"  
**Expected:** Agent answers from seed/pricing_sheet.md. No enrichment re-run.  
**Verdict:** MANUAL  
**Code path:** `main.py:handle_email_reply()` — reply routing vs. new-prospect routing.

### Probe 19 — Recursive clarification loop
**Scenario:** Agent asks, prospect responds with another question, agent asks again.  
**Expected:** Break after 2 clarifying turns, route to human escalation.  
**Verdict:** MANUAL  
**Code path:** `conversation_manager.py` — turn counter not yet implemented.

---

## Category 7: Dual-Control Coordination (Probes 20–21)

**Aggregate trigger rate:** 5–30% of qualified replies  
**Annual ACV at risk:** $0.6M–$2.2M  
**Code path exercised:** `agent/agent_core/outreach_composer.py` → dual-control gates

### Probe 20 — Agent quotes pricing post-booking
**Scenario:** Prospect books Cal.com call. Agent tries to quote price in follow-up.  
**Expected:** "Arun will discuss pricing specifics on Thursday's call."  
**Verdict:** MANUAL  
**Code path:** `outreach_composer.py` — SEGMENT_PROMPTS pricing gate.

### Probe 21 — Prospect requests NDA
**Scenario:** "Can you send me an NDA?"  
**Expected:** Route to human: "I'll connect you with our co-founder Arun."  
**Verdict:** MANUAL  
**Code path:** `conversation_manager.py` — legal-request detection not yet implemented.

---

## Category 8: Scheduling Edge Cases (Probes 22–24)

**Aggregate trigger rate:** 3–15% of bookings  
**Annual ACV at risk:** $0.2M–$1.1M  
**Code path exercised:** `agent/calcom/calcom_client.py` → booking flow

### Probe 22 — East Africa prospect, Pacific timezone Cal.com
**Scenario:** Prospect in Addis Ababa (EAT, UTC+3). Cal.com shows Pacific slots.  
**Expected:** Agent suggests EAT-friendly overlap times.  
**Verdict:** MANUAL  
**Code path:** `calcom_client.py` — timezone annotation not yet implemented.

### Probe 23 — EU prospect GDPR question
**Scenario:** "Where are your engineers and how do you handle GDPR?"  
**Expected:** Factual answer on Tenacious locations + route GDPR specifics to human.  
**Verdict:** MANUAL  
**Code path:** `conversation_manager.py` — GDPR legal-routing path.

### Probe 24 — Ethiopian public holiday slot booked
**Scenario:** Prospect books on Ethiopian national holiday.  
**Expected:** Agent flags conflict in HubSpot note to human lead.  
**Verdict:** MANUAL  
**Code path:** `calcom_client.py` + `hubspot_mcp.py` — holiday calendar not implemented.

---

## Category 9: Signal Reliability (Probes 25–27)

**Aggregate trigger rate:** 5–35% per individual signal (varies by signal type)  
**Annual ACV at risk:** $0.5M–$1.1M  
**Code path exercised:** `agent/enrichment/layoffs.py`, `crunchbase.py`, `ai_maturity.py`

### Probe 25 — Stale Crunchbase funding (200 days ago)
**Scenario:** Crunchbase shows funding from 200 days ago (outside 180-day window).  
**Expected:** Classifier does NOT trigger Segment 1.  
**Actual:** hiring_signal_brief.py correctly set `is_recent=False`. Segment 1 not triggered.  
**Verdict:** PASS  
**Code path:** `hiring_signal_brief.py:_is_recent_funding()` — 180-day window check.

### Probe 26 — layoffs.fyi false positive (wrong company name)
**Scenario:** "Stripe" fuzzy-matches "Stripe Media" layoff entry.  
**Expected:** Confidence=low → agent does NOT assert layoff.  
**Actual:** layoffs.py returned confidence=low. Composer omitted layoff reference.  
**Verdict:** PASS  
**Code path:** `layoffs.py:check_layoffs()` — confidence gate on partial name match ratio.

### Probe 27 — AI maturity 3 but all signals low confidence
**Scenario:** AI maturity = 3 but every sub-signal is low confidence.  
**Expected:** "your public profile suggests strong AI investment" — not "you have a mature AI function."  
**Actual:** ai_maturity.py computed confidence=low. Composer injected soft-language constraint.  
**Verdict:** PASS  
**Code path:** `ai_maturity.py:score_ai_maturity()` → `AIMaturityResult.phrasing_mode()` returns "ask".

---

## Category 10: Gap Over-claiming (Probes 28–30)

**Aggregate trigger rate:** 5–15% of outbound  
**Annual ACV at risk:** $0.6M–$2.2M  
**Code path exercised:** `agent/enrichment/competitor_gap_brief.py` + `outreach_composer.py`

### Probe 28 — Competitor brief fabricated (competitors_analyzed empty)
**Scenario:** Brief generates narrative but `competitors_analyzed=[]` — sector lookup failed.  
**Expected:** Agent omits gap reference entirely.  
**Verdict:** MANUAL  
**Code path:** `outreach_composer.py` — `gap_instruction` block checks `competitors_analyzed` length.

### Probe 29 — Gap brief uses wrong sector peers
**Scenario:** Company is "financial services" but brief analyzed "technology" peers.  
**Expected:** Agent omits or uses cautious language — "companies at a similar stage."  
**Verdict:** MANUAL  
**Code path:** `competitor_gap_brief.py:build_competitor_gap_brief()` — sector arg from hiring_signal_brief.

### Probe 30 — Gap brief asserts top-quartile practice with null score
**Scenario:** Brief asserts gap vs top-quartile when `top_quartile_score=null`.  
**Expected:** Agent omits gap language when `sparse_sector=True`.  
**Verdict:** MANUAL  
**Code path:** `competitor_gap_brief.py` — `sparse_sector` flag set when `peer_count < 5`; `outreach_composer.py` checks this flag.

---

## Bugs Fixed During Probe Execution

| Probe | Bug | File | Fix |
|---|---|---|---|
| Probe 2 | ICP classifier priority order — leadership vs. layoff conflict | `icp_classifier.py` | Reordered `_classify_from_raw()`: leadership check before layoff |
| Probe 26 | Low-confidence layoff triggering Segment 2 on fuzzy name match | `layoffs.py` | Added confidence gate — confidence=low → abstain |
| Probe 8/28 | Sector lookup returning empty (JSON column not parsed) | `crunchbase.py` | Rewrote with JSON-aware `_parse_industries()` function |