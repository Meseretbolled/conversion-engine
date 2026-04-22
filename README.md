# Tenacious Conversion Engine

> Automated lead generation and conversion system for Tenacious Consulting and Outsourcing.
> Week 10 — TRP1 Challenge | Interim Submission

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SIGNAL SOURCES (Public Data)                  │
│  Crunchbase ODM  │  Job Post Scraper  │  layoffs.fyi  │ Press   │
└────────┬─────────┴─────────┬──────────┴──────┬─────────┴────────┘
         │                   │                  │
         ▼                   ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              ENRICHMENT PIPELINE (agent/enrichment/)             │
│  hiring_signal_brief.json  +  competitor_gap_brief.json          │
│  AI Maturity Score (0–3)   +  ICP Segment Signals               │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│               ICP CLASSIFIER (agent/agent_core/)                 │
│  Segment 1: Recently-funded Series A/B                           │
│  Segment 2: Mid-market restructuring (post-layoff)               │
│  Segment 3: Engineering-leadership transition                     │
│  Segment 4: Specialized capability gap (AI maturity ≥ 2)         │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│             OUTREACH COMPOSER (agent/agent_core/)                │
│  Signal-grounded email per segment + pitch variant               │
│  Honesty constraints: no over-claiming on weak signals           │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ▼                          ▼ warm leads only
┌──────────────┐           ┌──────────────────┐
│    RESEND    │           │ AFRICA'S TALKING  │
│  (primary    │           │  SMS (secondary,  │
│   email)     │           │   scheduling)     │
└──────┬───────┘           └────────┬──────────┘
       │ reply webhook               │ inbound webhook
       └──────────────┬─────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│          CONVERSATION MANAGER (multi-turn, no leakage)           │
│  Qualify → Nurture → Offer booking link → Handle objections      │
└──────────────────────┬──────────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌─────────────────┐       ┌─────────────────────┐
│   CAL.COM       │       │   HUBSPOT CRM        │
│  Discovery call │       │  Contact + notes +   │
│  booking        │       │  enrichment fields   │
└─────────────────┘       └─────────────────────┘
                                    │
                                    ▼
                          ┌─────────────────────┐
                          │     LANGFUSE         │
                          │  Per-trace cost +    │
                          │  latency logging     │
                          └─────────────────────┘
```

---

## Project Structure

```
conversion-engine/
├── README.md                        ← you are here
├── .env.example                     ← copy to .env and fill in keys
├── docker-compose.yml               ← Cal.com + Postgres
│
├── agent/
│   ├── main.py                      ← FastAPI app (all webhooks)
│   ├── requirements.txt
│   │
│   ├── email_handler/
│   │   └── resend_client.py         ← Resend send + webhook verification
│   │
│   ├── sms_handler/
│   │   └── at_client.py             ← Africa's Talking send + parse inbound
│   │
│   ├── crm/
│   │   └── hubspot_mcp.py           ← HubSpot contacts + notes + bookings
│   │
│   ├── calendar/
│   │   └── calcom_client.py         ← Cal.com slots + booking creation
│   │
│   ├── enrichment/
│   │   ├── crunchbase.py            ← ODM sample lookup
│   │   ├── layoffs.py               ← layoffs.fyi checker
│   │   ├── job_scraper.py           ← Playwright job post scraper
│   │   ├── ai_maturity.py           ← AI maturity scorer (0–3)
│   │   ├── hiring_signal_brief.py   ← Merge all signals
│   │   └── competitor_gap_brief.py  ← Top-quartile gap analysis
│   │
│   ├── agent_core/
│   │   ├── llm_client.py            ← OpenRouter client + cost tracking
│   │   ├── icp_classifier.py        ← Segment 1–4 classification
│   │   ├── outreach_composer.py     ← Email composition per segment
│   │   └── conversation_manager.py  ← Multi-turn state + reply handling
│   │
│   └── observability/
│       └── langfuse_client.py       ← Tracing + span logging
│
├── eval/
│   ├── tau2_runner.py               ← τ²-Bench harness wrapper
│   ├── score_log.json               ← Baseline scores with 95% CIs
│   ├── trace_log.jsonl              ← Full evaluation trajectories
│   └── baseline.md                  ← Act I report (≤ 400 words)
│
├── data/
│   ├── crunchbase_sample.csv        ← Download separately (see below)
│   ├── layoffs.csv                  ← Download separately (see below)
│   └── briefs/                      ← Generated hiring + competitor briefs
│
├── scripts/
│   ├── verify_stack.py              ← Verify all integrations are live
│   └── test_prospect.py             ← End-to-end test with synthetic prospect
│
└── probes/                          ← Final submission (Days 4–7)
    ├── probe_library.md
    ├── failure_taxonomy.md
    └── target_failure_mode.md
```

---

## Setup Instructions

### Prerequisites
- Python 3.11+
- Docker Desktop (for Cal.com)
- Git

### Step 1 — Clone this repo and install dependencies

```bash
git clone <your-repo-url> conversion-engine
cd conversion-engine
pip install -r agent/requirements.txt
playwright install chromium
```

### Step 2 — Download required datasets

**Crunchbase ODM sample (1,001 records, Apache 2.0):**
```bash
# Option A: Direct download
curl -L "https://raw.githubusercontent.com/luminati-io/Crunchbase-dataset-samples/main/crunchbase_companies.csv" \
  -o data/crunchbase_sample.csv

# Option B: Clone the repo
git clone https://github.com/luminati-io/Crunchbase-dataset-samples tmp_cb
cp tmp_cb/*.csv data/crunchbase_sample.csv
rm -rf tmp_cb
```

**layoffs.fyi dataset (CC-BY):**
```bash
# Download CSV from https://layoffs.fyi
# Click the CSV download button on the site
# Save as: data/layoffs.csv
```

### Step 3 — Clone τ²-Bench

```bash
# Clone NEXT TO this repo (or adjust TAU2_DIR in eval/tau2_runner.py)
git clone https://github.com/sierra-research/tau2-bench ../tau2-bench
```

### Step 4 — Configure environment

```bash
cp .env.example .env
# Edit .env with your actual API keys:
# - RESEND_API_KEY (from resend.com dashboard)
# - AT_USERNAME + AT_API_KEY (from account.africastalking.com)
# - OPENROUTER_API_KEY (from openrouter.ai)
# - LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY (from cloud.langfuse.com)
# - HUBSPOT_ACCESS_TOKEN (from developers.hubspot.com — see HubSpot setup below)
```

### Step 5 — Set up HubSpot Developer Sandbox

1. Go to [developers.hubspot.com](https://developers.hubspot.com)
2. Sign up / log in → Create a **Developer Account**
3. Click **Create App** → give it a name
4. Go to **Auth** tab → Create a **Private App**
5. Scopes to enable: `crm.objects.contacts.write`, `crm.objects.contacts.read`, `crm.objects.notes.write`
6. Copy the **Private App token** → paste into `.env` as `HUBSPOT_ACCESS_TOKEN`

**Add custom properties to HubSpot contacts:**
- `crunchbase_id` (Single-line text)
- `icp_segment` (Single-line text)
- `ai_maturity_score` (Single-line text)
- `last_enriched_at` (Single-line text)
- `discovery_call_url` (Single-line text)
- `discovery_call_time` (Single-line text)

Go to: Settings → Properties → Contact properties → Create property

### Step 6 — Start Cal.com

```bash
docker compose up -d
# Wait ~2 minutes for first boot
# Open http://localhost:3000
# Create an admin account
# Create an event type called "Discovery Call" (30 min)
# Go to Settings → API Keys → Create key → paste into .env as CALCOM_API_KEY
# Note the event type ID → paste into .env as CALCOM_EVENT_TYPE_ID
```

### Step 7 — Verify everything is working

```bash
cd conversion-engine
# Set TEST_EMAIL and AT_TEST_NUMBER in .env first
python scripts/verify_stack.py
```

All 10 checks should pass before proceeding.

### Step 8 — Run τ²-Bench baseline (Act I)

```bash
cd conversion-engine
python eval/tau2_runner.py --tasks dev --trials 5 --tag baseline
# Results written to eval/score_log.json and eval/trace_log.jsonl
```

### Step 9 — Start the agent server

```bash
cd conversion-engine/agent
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/docs
```

### Step 10 — Test the full pipeline

```bash
cd conversion-engine
python scripts/test_prospect.py --company "Stripe" --skip-scraping
```

### Step 11 — Expose webhooks for Africa's Talking and Resend

Africa's Talking and Resend need to POST to your local server.
Use [ngrok](https://ngrok.com) (free) to create a public tunnel:

```bash
ngrok http 8000
# Copy the https URL e.g. https://abc123.ngrok.io
```

Configure webhooks:
- **Africa's Talking**: Dashboard → SMS → Callback URL → `https://abc123.ngrok.io/webhooks/sms/inbound`
- **Resend**: Dashboard → Webhooks → Add → `https://abc123.ngrok.io/webhooks/email/reply` → event: `email.replied`
- **Cal.com**: Settings → Developer → Webhooks → `https://abc123.ngrok.io/webhooks/calcom/booking`

---

## Kill Switch

Per the data-handling policy, all outbound is off by default in development.
Set `ENV=production` in `.env` only after Tenacious executive review.

In production, set `OUTBOUND_ENABLED=true` to enable real sending.
Default is `OUTBOUND_ENABLED=false` — all outbound routes to a staff sink.

---

## Cost Targets

| Layer | Budget | Actual (see Langfuse) |
|---|---|---|
| Dev-tier LLM (Days 1–4) | ≤ $4 | — |
| Eval-tier LLM (Days 5–7) | ≤ $12 | — |
| Total | ≤ $20 | — |

Cost per qualified lead target: **< $5** (Tenacious target).
Penalty applies if > $8 without justification.

---

## Channel Priority

Per challenge spec and Tenacious ICP (founders, CTOs, VPs Engineering):

1. **Email** (primary) — cold outreach, nurture sequence
2. **SMS** (secondary) — warm leads only, scheduling coordination
3. **Voice** (bonus) — discovery call delivered by human Tenacious delivery lead

---

## Data Sources

| Source | License | Path |
|---|---|---|
| Crunchbase ODM sample | Apache 2.0 | `data/crunchbase_sample.csv` |
| layoffs.fyi | CC-BY | `data/layoffs.csv` |
| τ²-Bench | Apache 2.0 | `../tau2-bench/` |

---

## Grading Observables (from challenge spec)

| Observable | How we address it |
|---|---|
| Reproduction fidelity | `eval/tau2_runner.py` reproduces retail baseline with pinned model |
| Probe originality | `probes/probe_library.md` (final submission) |
| Mechanism attribution | `eval/ablation_results.json` (final submission) |
| Cost-quality Pareto | Langfuse per-trace cost; target < $5/lead |
| Evidence-graph integrity | `evidence_graph.json` (final submission) |
| Skeptic's appendix | `memo.pdf` page 2 (final submission) |