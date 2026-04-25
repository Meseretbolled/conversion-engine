"""
scripts/test_prospect.py
End-to-end pipeline test for a single synthetic prospect.

Usage:
    # Full pipeline (with job scraping)
    python scripts/test_prospect.py --company "Stripe" --email test@yourdomain.com

    # Skip scraping (faster, uses cached/fallback signals)
    python scripts/test_prospect.py --company "Stripe" --email test@yourdomain.com --skip-scraping

    # Use the deployed Render instance instead of localhost
    python scripts/test_prospect.py --company "Stripe" --email test@yourdomain.com --base-url https://conversion-engine10.onrender.com

What this script tests end-to-end:
    1. Crunchbase ODM firmographic lookup
    2. Funding signal extraction
    3. Layoffs.fyi check
    4. Job post scraping (or skip)
    5. Leadership change detection
    6. AI maturity scoring (0–3)
    7. Competitor gap brief generation
    8. ICP segment classification
    9. Outreach email composition
   10. Email send via Resend (if OUTBOUND_ENABLED=true, else prints draft)
   11. HubSpot contact creation
   12. Console output: full brief + email draft

The script prints each step with timing so you can identify bottlenecks.
It NEVER sends to a real prospect — uses the staff sink unless OUTBOUND_ENABLED=true.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "agent"))


def _step(label: str):
    print(f"\n{'─'*52}\n{label}")


def _elapsed(t0: float) -> str:
    return f"{time.time() - t0:.2f}s"


def run_via_api(company: str, email: str, first_name: str, title: str,
                skip_scraping: bool, base_url: str):
    """Hit the live FastAPI /outreach/prospect endpoint and print results."""
    _step("Running via live API endpoint")
    print(f"  URL: {base_url}/outreach/prospect")

    payload = {
        "company_name":       company,
        "prospect_email":     email,
        "prospect_first_name": first_name,
        "prospect_title":     title,
        "skip_scraping":      skip_scraping,
    }

    t0 = time.time()
    try:
        r = requests.post(
            f"{base_url}/outreach/prospect",
            json=payload,
            timeout=120,
        )
    except requests.exceptions.ConnectionError:
        print(f"\n  ERROR: Cannot reach {base_url}")
        print("  Is the server running? Try: cd agent && uvicorn main:app --reload")
        sys.exit(1)

    elapsed = _elapsed(t0)
    print(f"  Status: {r.status_code}  ({elapsed})")

    if r.status_code != 200:
        print(f"  Error body: {r.text[:500]}")
        sys.exit(1)

    data = r.json()
    _print_results(data)
    return data


def run_directly(company: str, email: str, first_name: str, title: str,
                 skip_scraping: bool):
    """Import and run the pipeline directly in-process (no server required)."""
    from enrichment.hiring_signal_brief import build_hiring_signal_brief
    from enrichment.competitor_gap_brief import build_competitor_gap_brief
    from agent_core.icp_classifier import classify
    from agent_core.outreach_composer import compose_outreach_email

    _step("Step 1/6 — Hiring signal brief")
    t0 = time.time()
    brief = build_hiring_signal_brief(
        company_name=company,
        skip_scraping=skip_scraping,
    )
    print(f"  Done ({_elapsed(t0)})")
    print(f"  Crunchbase: {brief.get('crunchbase', {}).get('name', 'not found')}")
    print(f"  Funding:    {brief.get('funding_signal', {}).get('evidence', 'N/A')}")
    print(f"  Layoff:     {brief.get('layoff_signal', {}).get('evidence', 'N/A')}")
    print(f"  Jobs:       {brief.get('job_signal', {}).get('evidence', 'N/A')}")
    print(f"  Leadership: {brief.get('leadership_signal', {}).get('evidence', 'N/A')}")
    am = brief.get("ai_maturity", {})
    print(f"  AI maturity: {am.get('score', '?')}/3 ({am.get('confidence', '?')} confidence)")
    if brief.get("errors"):
        print(f"  Errors: {brief['errors']}")

    _step("Step 2/6 — Competitor gap brief")
    t0 = time.time()
    cb = brief.get("crunchbase") or {}
    sector = cb.get("industry") or "technology"
    # Use just the first industry tag for sector lookup
    if "," in str(sector):
        sector = sector.split(",")[0].strip()
    ai_signals = am.get("signals", [])
    comp_brief = build_competitor_gap_brief(
        company_name=company,
        sector=sector,
        prospect_ai_score=am.get("score", 0),
        prospect_ai_signals=ai_signals,
    )
    print(f"  Done ({_elapsed(t0)})")
    n_peers = len(comp_brief.get("competitors_analyzed", []))
    print(f"  Peers analyzed: {n_peers}")
    print(f"  Prospect position: {comp_brief.get('prospect_position', 'unknown')}")
    print(f"  Gaps found: {len(comp_brief.get('gaps', []))}")
    if comp_brief.get("errors"):
        print(f"  Errors: {comp_brief['errors']}")

    _step("Step 3/6 — ICP classification")
    t0 = time.time()
    icp = classify(brief)
    print(f"  Done ({_elapsed(t0)})")
    print(f"  Segment: {icp.segment} — {icp.segment_name}")
    print(f"  Confidence: {icp.confidence_label} ({icp.confidence:.2f})")
    print(f"  Pitch variant: {icp.pitch_variant}")
    if icp.disqualified:
        print(f"  DISQUALIFIED: {icp.disqualification_reason}")

    _step("Step 4/6 — Email composition")
    t0 = time.time()
    email_result = compose_outreach_email(
        icp_result=icp,
        hiring_brief=brief,
        competitor_brief=comp_brief,
        prospect_first_name=first_name,
        prospect_title=title,
    )
    print(f"  Done ({_elapsed(t0)})")

    _step("Step 5/6 — Email draft")
    print(f"\n  Subject: {email_result.get('subject', '[no subject]')}")
    print(f"\n  Body:\n")
    for line in (email_result.get("body") or "").split("\n"):
        print(f"    {line}")
    print(f"\n  Variant: {email_result.get('variant')}")
    print(f"  Confidence constraints applied: {email_result.get('confidence_notes')}")

    _step("Step 6/6 — Summary")
    outbound_enabled = os.getenv("TENACIOUS_OUTBOUND_ENABLED", "false").lower() == "true"
    if outbound_enabled:
        print("  OUTBOUND_ENABLED=true — email would be sent to real address")
        print("  NOTE: This script does not send email. Use /outreach/prospect endpoint.")
    else:
        print("  OUTBOUND_ENABLED=false (default) — email routed to staff sink")
        print("  Set TENACIOUS_OUTBOUND_ENABLED=true ONLY after Tenacious review")

    return {
        "hiring_brief": brief,
        "competitor_brief": comp_brief,
        "icp": icp.to_dict(),
        "email": email_result,
    }


def _print_results(data: dict):
    """Pretty-print results from the API endpoint."""
    _step("Results")
    print(json.dumps(data, indent=2, default=str)[:3000])


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end pipeline test for a single synthetic prospect"
    )
    parser.add_argument("--company",       required=True,  help="Company name to look up")
    parser.add_argument("--email",         required=True,  help="Prospect email (routed to staff sink by default)")
    parser.add_argument("--first-name",    default="there",  help="Prospect first name")
    parser.add_argument("--title",         default="",       help="Prospect job title")
    parser.add_argument("--skip-scraping", action="store_true", help="Skip Playwright job scraping")
    parser.add_argument("--base-url",      default="",       help="If set, call the live API instead of running in-process")
    parser.add_argument("--save",          action="store_true", help="Save briefs to data/briefs/")
    args = parser.parse_args()

    print(f"\nTenacious Conversion Engine — prospect test")
    print(f"Company:  {args.company}")
    print(f"Email:    {args.email} (routed to staff sink unless OUTBOUND_ENABLED=true)")
    print(f"Scraping: {'disabled' if args.skip_scraping else 'enabled'}")

    t_total = time.time()

    if args.base_url:
        result = run_via_api(
            company=args.company,
            email=args.email,
            first_name=args.first_name,
            title=args.title,
            skip_scraping=args.skip_scraping,
            base_url=args.base_url.rstrip("/"),
        )
    else:
        result = run_directly(
            company=args.company,
            email=args.email,
            first_name=args.first_name,
            title=args.title,
            skip_scraping=args.skip_scraping,
        )

    if args.save and result:
        out_dir = BASE_DIR / "data" / "briefs"
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = args.company.lower().replace(" ", "_")
        with open(out_dir / f"{slug}_hiring.json", "w") as f:
            json.dump(result.get("hiring_brief", {}), f, indent=2, default=str)
        with open(out_dir / f"{slug}_competitor.json", "w") as f:
            json.dump(result.get("competitor_brief", {}), f, indent=2, default=str)
        print(f"\n  Briefs saved to data/briefs/{slug}_*.json")

    print(f"\nTotal time: {_elapsed(t_total)}")
    print("Done.\n")


if __name__ == "__main__":
    main()