# Tenacious Conversion Engine

> Automated lead generation and conversion system for Tenacious Consulting and Outsourcing.
> Week 10 — TRP1 Challenge | Final Submission

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SIGNAL ENRICHMENT LAYER                          │
│                                                                         │
│  Crunchbase ODM ──► Funding Signal                                      │
│  layoffs.fyi    ──► Layoff Signal    ──► hiring_signal_brief.json       │
│  Playwright     ──► Job Velocity     ──► competitor_gap_brief.json      │
│  Crunchbase     ──► Leadership Change                                   │
│  Job Posts      ──► AI Maturity (0–3)                                   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      ICP CLASSIFICATION LAYER                           │
│                                                                         │
│  ICP Classifier ──► Segment 1 (funded)  / Segment 2 (restructuring)    │
│  (icp_classifier.py)  Segment 3 (new CTO) / Segment 4 (capability gap) │
│                       Abstain (low confidence)                          │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    OUTREACH COMPOSITION LAYER                           │
│                                                                         │
│  Signal-Confidence-Aware Phrasing (Python pre-LLM gate)                 │
│    high confidence → assert  │  medium → observe  │  low → ask/omit    │
│                                                                         │
│  Outreach Composer (outreach_composer.py) ──► OpenRouter LLM call      │
└──────┬─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       MULTI-CHANNEL DELIVERY LAYER                      │
│                                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────┐ │
│  │   Resend /   │   │ Africa's     │   │  Cal.com     │   │ HubSpot  │ │
│  │  MailerSend  │   │  Talking SMS │   │  (booking)   │   │   CRM    │ │
│  │  (email)     │   │  (warm only) │   │              │   │   MCP    │ │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └────┬─────┘ │
│         │ webhooks         │ inbound           │ bookings       │       │
│         └──────────────────┴──────────────────►│               │       │
│                                                │               │       │
│                  FastAPI Webhook Server (main.py) ─────────────►       │
└──────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        OBSERVABILITY LAYER                              │
│                                                                         │
│  Langfuse Cloud ──► per-trace cost attribution, p50/p95 latency        │
│  eval/trace_log.jsonl ──► τ²-Bench trajectory export                   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Channel priority (Tenacious ICP — founders, CTOs, VPs Engineering):**
1. **Email** (primary) — cold outreach and nurture via Resend / MailerSend
2. **SMS** (secondary) — warm leads only, scheduling coordination via Africa's Talking
3. **Voice** (bonus) — discovery call, booked by agent, delivered by human Tenacious lead

---

## Directory Index

```
conversion-engine/
│
├── README.md                    ← This file: architecture, setup, handoff
├── .env.example                 ← All required env vars with descriptions
├── requirements.txt             ← Python deps with pinned versions
├── docker-compose.yml           ← Cal.com self-hosted stack
├── memo.pdf                     ← 2-page decision memo (Act V)
├── evidence_graph.json          ← Every memo claim mapped to source
│
├── agent/                       ← FastAPI server + all agent logic
│   ├── main.py                  ← Webhook server, /outreach/prospect endpoint
│   ├── agent_core/
│   │   ├── icp_classifier.py    ← Segment 1-4 classification with confidence
│   │   ├── outreach_composer.py ← Signal-confidence-aware email composition
│   │   ├── conversation_manager.py ← Multi-turn state management
│   │   └── llm_client.py        ← OpenRouter client with Langfuse tracing
│   ├── enrichment/
│   │   ├── crunchbase.py        ← JSON-aware Crunchbase ODM lookup
│   │   ├── layoffs.py           ← layoffs.fyi match with confidence scoring
│   │   ├── job_scraper.py       ← Playwright job scraper (robots.txt aware)
│   │   ├── ai_maturity.py       ← 6-signal AI maturity scorer (0–3)
│   │   ├── hiring_signal_brief.py ← Merge all signals → hiring_signal_brief.json
│   │   └── competitor_gap_brief.py ← Top-quartile gap analysis
│   ├── email_handler/
│   │   ├── resend_client.py     ← Resend send + webhook signature verify
│   │   └── mailersend_client.py ← MailerSend alternative
│   ├── sms_handler/
│   │   └── at_client.py         ← Africa's Talking sandbox
│   ├── crm/
│   │   └── hubspot_mcp.py       ← HubSpot MCP contact + event logging
│   ├── calcom/
│   │   └── calcom_client.py     ← Cal.com booking flow
│   └── observability/
│       └── langfuse_client.py   ← Trace context + cost attribution
│
├── eval/                        ← τ²-Bench evaluation harness
│   ├── tau2_runner.py           ← Runner: saves score_log + trace_log
│   ├── score_log.json           ← Baseline + ablation scores with 95% CI
│   ├── trace_log.jsonl          ← Full τ²-Bench conversation trajectories
│   ├── ablation_results.json    ← v1/v2/v3 ablation with attribution
│   ├── baseline.md              ← Act I baseline report (max 400 words)
│   └── method.md                ← Act IV mechanism design documentation
│
├── probes/                      ← Act III adversarial probe library
│   ├── probe_library.md         ← 30 structured probes across 10 categories
│   ├── failure_taxonomy.md      ← Probes grouped by category + trigger rates
│   ├── target_failure_mode.md   ← Highest-ROI failure + business-cost derivation
│   ├── probe_runner.py          ← Automated probe execution
│   └── probe_results.json       ← Recorded probe verdicts
│
├── schemas/                     ← JSON schemas for brief formats
│   ├── hiring_signal_brief.schema.json
│   ├── competitor_gap_brief.schema.json
│   └── sample_*.json            ← Validated sample briefs
│
├── seed/                        ← Tenacious seed materials (challenge week only)
│   ├── icp_definition.md        ← 4 ICP segments with qualifiers/disqualifiers
│   ├── style_guide.md           ← 5 Tenacious tone markers
│   ├── bench_summary.json       ← Available engineers by stack (36 total)
│   ├── pricing_sheet.md         ← Public pricing bands by segment
│   ├── baseline_numbers.md      ← Published benchmarks + Tenacious internal rates
│   ├── email_sequences/         ← cold.md / warm.md / reengagement.md
│   └── discovery_transcripts/   ← 5 synthetic call transcripts
│
├── data/                        ← Public datasets
│   ├── crunchbase_sample.csv    ← 1,001 records, Apache 2.0
│   ├── layoffs.csv              ← layoffs.fyi CC-BY
│   └── briefs/                  ← Generated signal briefs (output)
│
├── scripts/
│   ├── verify_stack.py          ← Smoke-tests all 5 integrations
│   └── test_prospect.py         ← End-to-end pipeline test (single prospect)
│
├── assets/                      ← Screenshots for PDF report
└── policy/
    ├── data_handling_policy.md  ← Data governance rules
    └── acknowledgement.md       ← Signed policy acknowledgement
```

---

## Run Locally — Complete Setup (in order)

### Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.11+ | Check: `python --version` |
| pip | latest | `pip install --upgrade pip` |
| Docker Desktop | latest | Required for Cal.com |
| Git | any | For cloning τ²-Bench |
| Playwright | bundled | Installed via pip |

### Step 1 — Clone and install Python dependencies

```bash
git clone https://github.com/Meseretbolled/conversion-engine.git
cd conversion-engine
pip install -r requirements.txt
playwright install chromium
```

### Step 2 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in every key. Required keys and where to get them:

| Variable | Required | Where to get it |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | openrouter.ai → Keys |
| `RESEND_API_KEY` | Yes (or MailerSend) | resend.com → API Keys |
| `MAILERSEND_API_KEY` | Optional | mailersend.com → API Tokens |
| `AT_API_KEY` | Yes | africastalking.com → Sandbox → API Key |
| `AT_USERNAME` | Yes | "sandbox" for challenge week |
| `HUBSPOT_ACCESS_TOKEN` | Yes | HubSpot Developer Sandbox → Private App |
| `CALCOM_API_KEY` | Yes | Set after Step 3 |
| `CALCOM_BASE_URL` | Yes | `http://localhost:3000` for local |
| `LANGFUSE_PUBLIC_KEY` | Yes | cloud.langfuse.com → Project → API Keys |
| `LANGFUSE_SECRET_KEY` | Yes | cloud.langfuse.com → Project → API Keys |
| `LANGFUSE_HOST` | Yes | `https://cloud.langfuse.com` |
| `OUTBOUND_ENABLED` | No | Leave unset — routes to staff sink |

### Step 3 — Start Cal.com (Docker)

```bash
docker compose up -d
# Wait ~2 minutes for Cal.com to initialize
# Open http://localhost:3000
# Create admin account
# Create a "Discovery Call – 30min" event type
# Go to: Settings → Developer → API Keys → Add Key
# Copy key → add to .env as CALCOM_API_KEY
```

### Step 4 — Clone τ²-Bench into harness/

```bash
mkdir -p harness
git clone https://github.com/sierra-research/tau2-bench harness/tau2-bench
# Note: tau2-bench manages its own dependencies via uv
# You do NOT need to install its deps separately for the eval runner
```

### Step 5 — Verify all integrations

```bash
python scripts/verify_stack.py
```

Expected output — all five must show `[OK]`:
```
[OK]  Resend / MailerSend — email send + webhook reachable
[OK]  Africa's Talking — SMS sandbox credentials valid
[OK]  HubSpot Developer Sandbox — contact API reachable
[OK]  Cal.com — event types endpoint reachable
[OK]  Langfuse — project credentials valid
```

### Step 6 — Run τ²-Bench baseline

```bash
export OPENROUTER_API_KEY=your_key_here
export OPENAI_API_KEY=your_key_here
export OPENAI_API_BASE=https://openrouter.ai/api/v1

# Baseline (5 trials × 30 tasks — matches program baseline)
python eval/tau2_runner.py \
  --tag baseline \
  --trials 5 \
  --num-tasks 30

# Tenacious mechanism (Qwen3 model)
python eval/tau2_runner.py \
  --tag tenacious_method_v3 \
  --agent tenacious_agent \
  --agent-model openrouter/qwen/qwen3-next-80b-a3b-instruct \
  --user-model openrouter/qwen/qwen3-next-80b-a3b-instruct \
  --trials 1 \
  --num-tasks 30
```

Results auto-saved to `eval/score_log.json` and `eval/trace_log.jsonl`.

### Step 7 — Start the agent server

```bash
cd agent
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Step 8 — Test the full pipeline (one synthetic prospect)

```bash
# Quick test (skip job scraping for speed)
python scripts/test_prospect.py \
  --company "Stripe" \
  --email your@email.com \
  --first-name Alex \
  --title CTO \
  --skip-scraping \
  --save

# Or hit the API directly
curl -X POST http://localhost:8000/outreach/prospect \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Stripe",
    "prospect_email": "your@email.com",
    "prospect_first_name": "Alex",
    "prospect_title": "CTO",
    "skip_scraping": true
  }'
```

---

## Production Deployment (Render)

**Live URL:** `https://conversion-engine10.onrender.com`

| Webhook | URL |
|---|---|
| Resend (email replies) | `https://conversion-engine10.onrender.com/webhooks/email/reply` |
| Africa's Talking (SMS) | `https://conversion-engine10.onrender.com/webhooks/sms/inbound` |
| Cal.com (bookings) | `https://conversion-engine10.onrender.com/webhooks/calcom/booking` |

> **Note:** Render free tier has a ~50s cold-start on the first request after inactivity. This is documented in the p95 latency figures (production p95 = 8.41s, excludes cold start).

---

## Kill Switch

All outbound is **disabled by default** per the data-handling policy.

```bash
# .env
OUTBOUND_ENABLED=false    # default — all outbound routes to staff sink
ENV=development           # set to "production" ONLY after Tenacious review
```

**Automatic triggers** that disable outbound:
- Wrong-signal complaint rate > 2% in any 7-day window
- Bench over-commitment detected (agent commits to more than bench shows)
- Reply rate drops below 1% for 3 consecutive days

---

## ICP Segments

| Segment | Qualifying Signal | Pitch |
|---|---|---|
| 1 — Recently funded | Series A/B in last 180 days, $5–30M | Scale engineering faster than in-house hiring |
| 2 — Restructuring | Layoff in last 120 days, 200–2,000 employees | Replace higher-cost roles with offshore equivalent |
| 3 — Leadership transition | New CTO/VP Eng in last 90 days | Vendor reassessment window — first 6 months |
| 4 — Capability gap | AI maturity ≥ 2 | ML platform, agentic systems, data contracts |
| Abstain | Confidence < threshold or disqualifier hit | Generic exploratory email only |

---

## τ²-Bench Baseline

| Metric | Value | Source |
|---|---|---|
| Domain | retail | τ²-Bench |
| Program baseline pass@1 | **72.67%** | eval/score_log.json |
| 95% CI | [65.04%, 79.17%] | eval/score_log.json |
| tenacious_method_v3 pass@1 | **56.67%** | eval/score_log.json |
| 95% CI (v3) | [39.20%, 72.62%] | eval/score_log.json |
| Published reference | 42.00% (GPT-5 class) | τ²-Bench leaderboard Feb 2026 |
| Cost per conversation | $0.0199 | eval/score_log.json |

---

## Cost Envelope

| Layer | Budget | Actual |
|---|---|---|
| Dev-tier LLM (Days 1–4) | ≤ $4 | ~$3.20 |
| Eval-tier LLM (Days 5–7) | ≤ $12 | ~$8.40 |
| Total | ≤ $20 | ~$11.60 |
| Cost per qualified lead | < $5 (Tenacious target) | ~$2.80 |

---

## Data Sources

| Source | License | Path |
|---|---|---|
| Crunchbase ODM sample | Apache 2.0 | `data/crunchbase_sample.csv` |
| layoffs.fyi | CC-BY | `data/layoffs.csv` |
| τ²-Bench | Apache 2.0 | `harness/tau2-bench/` |

---

## Handoff Notes for the Inheriting Engineer

### What works and has been tested
- All 5 integrations (Resend, Africa's Talking, HubSpot MCP, Cal.com, Langfuse) verified against live sandboxes
- Signal enrichment pipeline produces valid `hiring_signal_brief.json` for 27 tested prospects
- ICP classifier correctly handles all 4 segment conflict cases (see probe_library.md)
- Signal-confidence-aware phrasing prevents over-claiming on weak signals (10/10 automated probes pass)
- Crunchbase sector lookup uses JSON-aware parsing (fixed from naive string match)

### Known limitations to fix before production
1. **20/30 probes are MANUAL** — bench over-commitment (probes 9–12), tone drift (13–15), multi-thread leakage (16–17), scheduling edge cases (22–24), and gap over-claiming (28–30) have not been run through the automated pipeline. Each needs a conversation replay fixture.
2. **Tone-preservation check is designed but not deployed** — the second LLM call that scores draft emails against the 5 style-guide markers is in `eval/method.md` Section 3 but not wired into `outreach_composer.py`. Estimated 1 day to implement.
3. **Delta A is negative on τ²-Bench** — the Tenacious agent scores 56.67% vs the 72.67% program baseline. Root causes are trial count (1 vs 5 trials) and domain mismatch (retail benchmark penalizes honesty deferrals). See `eval/method.md` Section 5.3 for full explanation. Not a production blocker.
4. **Render free-tier cold start** — first request after inactivity takes ~50s. Use a paid Render instance or a keep-alive ping for production.
5. **Job scraper respects robots.txt** but some target companies (e.g., LinkedIn) block scraping. The fallback returns `total_open_roles=0` and the agent correctly asks rather than asserts. No data to enrich from those companies.

### Next steps for Tenacious pilot
1. Obtain written approval from Tenacious executive team and set `OUTBOUND_ENABLED=true`
2. Start with Segment 1 only (recently funded) — smallest risk, highest signal quality
3. Run 50 prospects/week for 4 weeks, track reply rate and stalled-thread rate
4. Success criterion: reply rate ≥ 5% (above 1–3% generic baseline), stalled-thread rate ≤ 20%
5. Pause if wrong-signal complaint rate exceeds 2% (kill-switch threshold)

### Environment and dependencies
- Python 3.11 required (not 3.12 — τ²-Bench uses 3.12 internally but the agent stack uses 3.11)
- All pip deps pinned in `requirements.txt`
- Docker Desktop required only for local Cal.com — production uses the Render-deployed instance
- τ²-Bench must be cloned separately (too large for the repo); path: `harness/tau2-bench/`