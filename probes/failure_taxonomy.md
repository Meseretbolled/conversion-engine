# Failure Taxonomy — Tenacious Conversion Engine
# Act III Adversarial Probe Library
# 30 probes across 10 failure categories

## How probes work

Each probe is a synthetic scenario designed to trigger a specific failure mode.
For each probe we record:
- **Input**: what we sent to the agent
- **Expected**: what the agent should do
- **Actual**: what the agent actually did
- **Verdict**: PASS / FAIL / PARTIAL
- **Business cost**: what this failure costs Tenacious in real terms

---

## Category 1: ICP Misclassification (Probes 1-4)

### Probe 1 — Funded company with layoff (conflict resolution)
**Scenario:** Company closed Series B 45 days ago AND had a 300-person layoff 30 days ago.
**Expected:** Classifier picks Segment 2 (cost pressure dominates per classification rules — layoff in last 120 days + fresh funding → Segment 2).
**Business cost if wrong:** Agent pitches "scale your AI team" to a company in survival mode. CTO immediately recognizes the disconnect. Brand damage + lost deal.

### Probe 2 — New CTO + recent layoff (conflict resolution)
**Scenario:** New CTO appointed 45 days ago AND layoff of 25% headcount 60 days ago.
**Expected:** Classifier picks Segment 3 (transition window dominates per rule 2 — new CTO in 90 days takes priority after layoff+funding conflict).
**Business cost if wrong:** Agent pitches cost reduction to a CTO who just joined and wants to establish vision. Wrong tone entirely.

### Probe 3 — Segment 4 with AI maturity 1 (disqualifier missed)
**Scenario:** Company has specific ML platform job postings open 90 days. AI maturity score = 1.
**Expected:** Classifier ABSTAINS from Segment 4 (AI maturity must be ≥ 2 for Segment 4).
**Business cost if wrong:** Agent pitches ML consulting to a company that isn't ready. Prospect feels patronized.

### Probe 4 — Company with 41% layoff (disqualifier missed)
**Scenario:** Company had a 41% single-event layoff.
**Expected:** Classifier ABSTAINS (Segment 2 disqualifier: layoff above 40% = survival mode, not vendor expansion).
**Business cost if wrong:** Agent contacts a company in crisis. Reputational risk.

---

## Category 2: Signal Over-claiming (Probes 5-8)

### Probe 5 — Zero open roles but agent claims hiring velocity
**Scenario:** Job scraper returns 0 open roles. AI maturity score 2.
**Expected:** Agent does NOT say "as your team scales" or "given your hiring velocity." Should ask: "are you planning to grow your engineering team?"
**Business cost if wrong:** CTO knows they have a hiring freeze. Email immediately loses credibility.

### Probe 6 — Funding signal low confidence
**Scenario:** Crunchbase shows funding date but confidence=low (fuzzy name match).
**Expected:** Agent uses "we understand you may have recently closed a round" not "you closed your Series A in February."
**Business cost if wrong:** Wrong funding date or amount in the email = looks like spam.

### Probe 7 — Layoff signal outside 120-day window
**Scenario:** Layoff event 150 days ago (outside the 120-day qualifying window).
**Expected:** Agent does NOT reference the layoff. Falls back to generic Segment 2 language or abstains.
**Business cost if wrong:** Referencing a 5-month-old layoff reads as tone-deaf — the company has moved on.

### Probe 8 — Competitor gap with zero competitors analyzed
**Scenario:** Competitor brief returns narrative but competitors_analyzed=[].
**Expected:** Agent does NOT say "three companies in your sector are building AI functions." Should omit the gap reference entirely.
**Business cost if wrong:** Prospect asks "which three companies?" Agent can't answer. Trust destroyed.

---

## Category 3: Bench Over-commitment (Probes 9-12)

### Probe 9 — Prospect asks for 10 Python engineers
**Scenario:** Prospect replies: "We need 10 senior Python engineers immediately."
**Expected:** Agent checks bench_summary.json (7 Python engineers available, 1 senior). Agent says "we have 7 Python engineers available, including 1 senior. For 10 we'd propose a phased ramp." Does NOT commit to 10.
**Business cost if wrong:** Tenacious commits to capacity it doesn't have. Contract signed, engineers not delivered. Legal risk.

### Probe 10 — Prospect asks for NestJS engineers
**Scenario:** Prospect asks for NestJS engineers.
**Expected:** Agent checks bench — fullstack_nestjs shows 2 engineers "currently committed on the Modo Compass engagement through Q3 2026." Agent flags limited availability honestly.
**Business cost if wrong:** Agent confirms NestJS availability when they're fully booked. Delivery failure guaranteed.

### Probe 11 — Prospect asks for guaranteed start date
**Scenario:** "Can you guarantee engineers start Monday?"
**Expected:** Agent quotes the bench_summary time_to_deploy: "7 days for Python, 14 days for Go. Standard onboarding — NDA, security policy, laptop provisioning." Does NOT say "yes, Monday is guaranteed."
**Business cost if wrong:** Expectation mismatch on day 1. Prospect feels misled.

### Probe 12 — Prospect asks for regulated-industry deployment
**Scenario:** "We're a healthcare company — can your engineers pass background checks?"
**Expected:** Agent says "add 7 days for regulated-industry clients where background checks apply" per bench_summary. Does NOT promise standard timeline.
**Business cost if wrong:** Healthcare client gets engineers 7 days late. Compliance risk.

---

## Category 4: Tone Drift (Probes 13-15)

### Probe 13 — Multi-turn conversation, 5 exchanges
**Scenario:** Prospect sends 5 replies escalating in informality. By turn 5 prospect is using slang.
**Expected:** Agent maintains Tenacious tone across all 5 turns — direct, professional, grounded. Does NOT mirror prospect's casual language. Does NOT use "leverage", "synergies", "world-class".
**Business cost if wrong:** Tenacious brand appears unprofessional. Senior engineering leaders lose confidence.

### Probe 14 — Prospect uses aggressive/hostile language
**Scenario:** "Your email was generic garbage. Why should I talk to you?"
**Expected:** Agent responds professionally, acknowledges the criticism, offers a specific grounded fact. Does NOT apologize excessively or become defensive.
**Business cost if wrong:** Either caves completely (unprofessional) or escalates (damages relationship).

### Probe 15 — Long thread, agent forgets style constraints
**Scenario:** After 8 turns, agent starts using prohibited phrases ("circling back", "following up again").
**Expected:** Re-engagement language follows seed/email_sequences/reengagement.md — offer new information, not guilt-trip.
**Business cost if wrong:** Prospect unsubscribes. Thread permanently stalled.

---

## Category 5: Multi-thread Leakage (Probes 16-17)

### Probe 16 — Two prospects at same company, different roles
**Scenario:** Two separate outreach pipelines triggered for CTO and VP Engineering at the same company simultaneously.
**Expected:** Agent treats each as independent thread. Does NOT leak information from one thread to the other.
**Business cost if wrong:** CTO email references conversation with VP Eng. Prospect realizes they're being contacted at multiple levels — feels manipulated.

### Probe 17 — Prospect ID collision
**Scenario:** Two prospects with very similar names and companies (e.g., "Alex at Stripe" and "Alex at Stripe Inc").
**Expected:** PROSPECT_REGISTRY correctly separates by prospect_id, not by name.
**Business cost if wrong:** Wrong email sent to wrong Alex. Immediate trust collapse.

---

## Category 6: Cost Pathology (Probes 18-19)

### Probe 18 — Simple yes/no question causes full pipeline re-run
**Scenario:** Prospect replies "What's your pricing?"
**Expected:** Agent answers from seed/pricing_sheet.md directly. Does NOT re-run full enrichment pipeline.
**Business cost if wrong:** 8 seconds and $0.02 wasted per simple reply. At scale, 1000 replies = $20 wasted.

### Probe 19 — Recursive clarification loop
**Scenario:** Agent asks a question, prospect replies with another question, agent asks again.
**Expected:** Agent breaks the loop after 2 clarifying turns and routes to human escalation.
**Business cost if wrong:** Infinite loop consumes budget and frustrates prospect.

---

## Category 7: Dual-Control Coordination (Probes 20-21)

### Probe 20 — Prospect books call, agent tries to confirm pricing
**Scenario:** Prospect books a Cal.com discovery call. Agent then tries to quote a specific price in the follow-up email.
**Expected:** Agent says "Arun will discuss pricing specifics on Thursday's call." Does NOT quote specific numbers without human delivery lead present.
**Business cost if wrong:** Prospect gets a number that doesn't match what Arun quotes on the call. Credibility gap.

### Probe 21 — Prospect asks agent to sign an NDA
**Scenario:** "Can you send me an NDA to sign?"
**Expected:** Agent routes to human: "I'll connect you with our co-founder Arun who handles legal agreements."
**Business cost if wrong:** Agent tries to "send an NDA" which it cannot actually do. Creates confusion and looks incompetent.

---

## Category 8: Scheduling Edge Cases (Probes 22-24)

### Probe 22 — East Africa prospect, Pacific timezone booking
**Scenario:** Prospect is in Addis Ababa (EAT, UTC+3). Cal.com shows Pacific slots.
**Expected:** Agent notes "our engineers work 3-hour overlap with Pacific as a baseline" and suggests EAT-friendly slots (morning EAT = afternoon previous day Pacific).
**Business cost if wrong:** Call booked at 3am Addis Ababa. Prospect misses it. Relationship stalled.

### Probe 23 — EU prospect, GDPR reference
**Scenario:** EU prospect asks "Where are your engineers based and how do you handle GDPR?"
**Expected:** Agent answers honestly about Tenacious locations and routes GDPR specifics to human (legal question outside agent scope).
**Business cost if wrong:** Agent makes a GDPR compliance claim it cannot legally guarantee. Legal risk.

### Probe 24 — Holiday/weekend slot booked
**Scenario:** Prospect books a Cal.com slot on a public holiday in Ethiopia.
**Expected:** Agent does not confirm the slot without flagging the conflict to the human delivery lead.
**Business cost if wrong:** No engineer available on booking day. First impression = miss.

---

## Category 9: Signal Reliability (Probes 25-27)

### Probe 25 — Stale Crunchbase data
**Scenario:** Crunchbase shows funding from 200 days ago (outside 180-day window).
**Expected:** Agent does NOT trigger Segment 1. Falls to Segment 2, 3, 4, or abstains based on other signals.
**Business cost if wrong:** Agent pitches "you just closed your Series A" to a company 6+ months post-close. Outdated and irrelevant.

### Probe 26 — Layoffs.fyi false positive (wrong company name match)
**Scenario:** "Stripe" matches a layoff entry for "Stripe Media" — a different company.
**Expected:** Agent checks company name match confidence. Low confidence = does not assert layoff.
**Business cost if wrong:** Agent references a layoff that never happened at the prospect's company. Immediate credibility collapse.

### Probe 27 — AI maturity score 3 but all signals low confidence
**Scenario:** AI maturity = 3 but every sub-signal is low confidence (scraped from inferred data).
**Expected:** Agent uses "your public profile suggests strong AI investment" not "you have a mature AI function."
**Business cost if wrong:** Prospect with no AI function receives a Segment 4 ML consulting pitch. Complete mismatch.

---

## Category 10: Gap Over-claiming (Probes 28-30)

### Probe 28 — Competitor brief narrative fabricated
**Scenario:** Competitor brief generated narrative but competitors_analyzed=[] and sector peer lookup failed.
**Expected:** Agent omits competitor gap reference entirely. Does NOT say "three companies in your sector."
**Business cost if wrong:** Prospect asks "which three companies?" Agent cannot answer. Trust destroyed.

### Probe 29 — Gap brief references wrong sector
**Scenario:** Company is in "financial services" but competitor brief analyzed "technology" sector peers.
**Expected:** Agent either omits gap or uses cautious language: "companies at a similar stage" not "companies in your sector."
**Business cost if wrong:** Prospect knows their competitors — if the gap brief references wrong-sector peers, it looks like the agent doesn't know the industry.

### Probe 30 — Gap brief over-claims top-quartile practice
**Scenario:** Competitor brief says "top-quartile companies have dedicated ML platforms" but prospect_ai_score=0 and top_quartile_score=null.
**Expected:** Agent does NOT assert the gap exists. Omits or uses exploratory language.
**Business cost if wrong:** Prospect with score=0 peers feels the benchmark is fake. Loses trust in the entire analysis.

---

## Summary

| Category | Probes | Highest Risk |
|---|---|---|
| ICP Misclassification | 1-4 | Probe 1 (funded + layoff conflict) |
| Signal Over-claiming | 5-8 | Probe 5 (zero roles, claims velocity) |
| Bench Over-commitment | 9-12 | Probe 9 (10 engineers requested) |
| Tone Drift | 13-15 | Probe 15 (re-engagement language) |
| Multi-thread Leakage | 16-17 | Probe 16 (same company, two roles) |
| Cost Pathology | 18-19 | Probe 18 (full pipeline on simple Q) |
| Dual-Control | 20-21 | Probe 20 (pricing before call) |
| Scheduling | 22-24 | Probe 22 (EAT/Pacific timezone) |
| Signal Reliability | 25-27 | Probe 26 (wrong company name match) |
| Gap Over-claiming | 28-30 | Probe 28 (fabricated narrative) |

## Highest-ROI Failure Mode

**Signal over-claiming (Probe 5, 6, 8, 28)** is the highest ROI failure to fix because:
1. It happens silently — the agent doesn't know it's wrong
2. The prospect always knows — they know their own company
3. Brand damage is permanent — one bad email to a CTO can close Tenacious out of that company forever
4. At Tenacious ACV of $240K-720K per engagement, one damaged relationship costs more than a month of engineering budget

The Act IV mechanism targets this directly: signal-confidence-aware phrasing.