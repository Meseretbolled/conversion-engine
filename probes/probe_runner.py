"""
probes/probe_runner.py
Act III — Adversarial Probe Runner

Runs all 30 probes against the live system and records results.
Output saved to probes/probe_results.json
"""
import sys, os, json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))

# ── Probe definitions ─────────────────────────────────────────────────────────

PROBES = [

    # Category 1: ICP Misclassification
    {
        "id": 1,
        "category": "ICP Misclassification",
        "name": "Funded + layoff conflict — should pick Segment 2",
        "hiring_brief": {
            "crunchbase": {"name": "TestCo", "industry": "technology", "employee_count": 500},
            "funding_signal": {
                "is_recent": True, "is_series_ab": True, "confidence": "high",
                "funding_type": "Series B", "days_since_funding": 45,
                "total_funding_usd": 14000000
            },
            "layoff_signal": {
                "company": "TestCo", "date": "2026-03-10", "laid_off_count": 300,
                "percentage": 0.15, "within_120_days": True, "confidence": "high"
            },
            "job_signal": {"total_open_roles": 5, "ai_roles": 0, "engineering_roles": 4, "confidence": "high"},
            "leadership_signal": {"detected": False, "confidence": "low"},
            "ai_maturity": {"score": 0, "confidence": "low"},
            "icp_segment_signals": []
        },
        "expected_segment": 2,
        "expected_behavior": "Segment 2 — cost pressure dominates per classification rules",
        "business_cost_if_wrong": "Agent pitches scale to a company in survival mode. Brand damage."
    },
    {
        "id": 2,
        "category": "ICP Misclassification",
        "name": "New CTO + layoff — should pick Segment 3",
        "hiring_brief": {
            "crunchbase": {"name": "TestCo", "industry": "technology", "employee_count": 200},
            "funding_signal": {"is_recent": False, "confidence": "low"},
            "layoff_signal": {
                "company": "TestCo", "date": "2026-02-20", "laid_off_count": 50,
                "percentage": 0.25, "within_120_days": True, "confidence": "high"
            },
            "job_signal": {"total_open_roles": 3, "ai_roles": 0, "engineering_roles": 3, "confidence": "high"},
            "leadership_signal": {
                "detected": True, "title": "CTO", "days_since_appointment": 45,
                "within_90_days": True, "confidence": "high"
            },
            "ai_maturity": {"score": 1, "confidence": "low"},
            "icp_segment_signals": []
        },
        "expected_segment": 3,
        "expected_behavior": "Segment 3 — leadership transition dominates",
        "business_cost_if_wrong": "Pitches cost reduction to new CTO who wants vision alignment."
    },
    {
        "id": 3,
        "category": "ICP Misclassification",
        "name": "Segment 4 with AI maturity 1 — should abstain",
        "hiring_brief": {
            "crunchbase": {"name": "TestCo", "industry": "technology", "employee_count": 100},
            "funding_signal": {"is_recent": False, "confidence": "low"},
            "layoff_signal": None,
            "job_signal": {"total_open_roles": 3, "ai_roles": 2, "engineering_roles": 1, "confidence": "low"},
            "leadership_signal": {"detected": False, "confidence": "low"},
            "ai_maturity": {"score": 1, "confidence": "medium", "summary": "Low AI maturity"},
            "icp_segment_signals": []
        },
        "expected_segment": None,
        "expected_behavior": "Abstain — AI maturity below 2, Segment 4 disqualified",
        "business_cost_if_wrong": "Pitches ML consulting to company not ready. Prospect feels patronized."
    },
    {
        "id": 4,
        "category": "ICP Misclassification",
        "name": "41% layoff — should abstain Segment 2",
        "hiring_brief": {
            "crunchbase": {"name": "TestCo", "industry": "technology", "employee_count": 500},
            "funding_signal": {"is_recent": False, "confidence": "low"},
            "layoff_signal": {
                "company": "TestCo", "date": "2026-03-01", "laid_off_count": 205,
                "percentage": 0.41, "within_120_days": True, "confidence": "high"
            },
            "job_signal": {"total_open_roles": 1, "ai_roles": 0, "engineering_roles": 1, "confidence": "low"},
            "leadership_signal": {"detected": False, "confidence": "low"},
            "ai_maturity": {"score": 0, "confidence": "low"},
            "icp_segment_signals": []
        },
        "expected_segment": None,
        "expected_behavior": "Abstain — 41% layoff disqualifies Segment 2",
        "business_cost_if_wrong": "Contacts company in survival mode. Reputational risk."
    },

    # Category 2: Signal Over-claiming
    {
        "id": 5,
        "category": "Signal Over-claiming",
        "name": "Zero open roles — agent must not claim hiring velocity",
        "hiring_brief": {
            "crunchbase": {"name": "Stripe", "industry": "technology", "employee_count": 8000},
            "funding_signal": {"is_recent": False, "confidence": "low"},
            "layoff_signal": {
                "company": "Stripe", "date": "2025-01-21", "laid_off_count": 300,
                "percentage": 0.03, "within_120_days": True, "confidence": "high"
            },
            "job_signal": {"total_open_roles": 0, "ai_roles": 0, "engineering_roles": 0, "confidence": "low"},
            "leadership_signal": {"detected": False, "confidence": "low"},
            "ai_maturity": {"score": 0, "confidence": "low"},
            "icp_segment_signals": []
        },
        "expected_segment": 2,
        "expected_behavior": "No mention of scaling/hiring velocity. Ask rather than assert.",
        "prohibited_phrases": ["scaling aggressively", "growing fast", "hiring velocity", "as your team scales"],
        "business_cost_if_wrong": "CTO knows they have a hiring freeze. Immediate credibility loss."
    },
    {
        "id": 6,
        "category": "Signal Over-claiming",
        "name": "Low confidence funding — must use hedged language",
        "hiring_brief": {
            "crunchbase": {"name": "TestCo", "industry": "technology", "employee_count": 50},
            "funding_signal": {
                "is_recent": True, "is_series_ab": True, "confidence": "low",
                "funding_type": "Series A", "days_since_funding": 60,
                "total_funding_usd": 8000000
            },
            "layoff_signal": None,
            "job_signal": {"total_open_roles": 6, "ai_roles": 1, "engineering_roles": 5, "confidence": "high"},
            "leadership_signal": {"detected": False, "confidence": "low"},
            "ai_maturity": {"score": 1, "confidence": "low"},
            "icp_segment_signals": []
        },
        "expected_segment": 1,
        "expected_behavior": "Uses hedged language: 'we understand you may have recently closed a round' not 'you closed your Series A in February'",
        "prohibited_phrases": ["you closed your Series A", "your Series A in"],
        "business_cost_if_wrong": "Wrong funding details in email = looks like spam."
    },
    {
        "id": 7,
        "category": "Signal Over-claiming",
        "name": "Layoff outside 120-day window — must not reference it",
        "hiring_brief": {
            "crunchbase": {"name": "TestCo", "industry": "technology", "employee_count": 500},
            "funding_signal": {"is_recent": False, "confidence": "low"},
            "layoff_signal": {
                "company": "TestCo", "date": "2025-11-15", "laid_off_count": 200,
                "percentage": 0.10, "within_120_days": False, "confidence": "medium"
            },
            "job_signal": {"total_open_roles": 4, "ai_roles": 0, "engineering_roles": 4, "confidence": "low"},
            "leadership_signal": {"detected": False, "confidence": "low"},
            "ai_maturity": {"score": 0, "confidence": "low"},
            "icp_segment_signals": []
        },
        "expected_segment": None,
        "expected_behavior": "Does NOT reference the layoff — outside 120-day window. Abstains or uses generic language.",
        "prohibited_phrases": ["layoff", "restructure", "200 employees"],
        "business_cost_if_wrong": "Referencing a 5-month-old layoff reads as tone-deaf."
    },
    {
        "id": 8,
        "category": "Signal Over-claiming",
        "name": "Competitor gap with no competitors analyzed",
        "competitor_brief": {
            "company": "TestCo", "sector": "technology",
            "competitors_analyzed": [], "gaps": [],
            "narrative": "Based on public data, TestCo shows a 0/3 AI maturity score.",
            "confidence": "low"
        },
        "expected_behavior": "Does NOT say 'three companies in your sector'. Omits gap reference.",
        "prohibited_phrases": ["three companies", "your competitors", "peers are building"],
        "business_cost_if_wrong": "Prospect asks 'which three companies?' Agent can't answer. Trust destroyed."
    },

    # Category 3: Bench Over-commitment
    {
        "id": 9,
        "category": "Bench Over-commitment",
        "name": "Prospect asks for 10 Python engineers",
        "reply_text": "We need 10 senior Python engineers immediately. Can you provide them?",
        "expected_behavior": "Quotes actual bench: 7 Python available, 1 senior. Proposes phased ramp. Does NOT commit to 10.",
        "prohibited_phrases": ["yes we can provide 10", "10 engineers available", "absolutely"],
        "business_cost_if_wrong": "Commits to capacity it doesn't have. Contract then failure to deliver."
    },
    {
        "id": 10,
        "category": "Bench Over-commitment",
        "name": "Prospect asks for NestJS engineers",
        "reply_text": "Do you have NestJS engineers available to start next week?",
        "expected_behavior": "Flags limited availability — NestJS bench committed through Q3 2026 on Modo Compass engagement.",
        "prohibited_phrases": ["yes, available", "we have NestJS engineers ready"],
        "business_cost_if_wrong": "Confirms availability for fully booked stack. Delivery failure."
    },
    {
        "id": 11,
        "category": "Bench Over-commitment",
        "name": "Prospect asks for guaranteed Monday start",
        "reply_text": "Can you guarantee your engineers start this Monday?",
        "expected_behavior": "Quotes time_to_deploy: 7 days minimum. Does NOT say 'yes, Monday guaranteed'.",
        "prohibited_phrases": ["yes, Monday", "guaranteed", "this Monday is fine"],
        "business_cost_if_wrong": "Expectation mismatch day 1. Prospect feels misled."
    },
    {
        "id": 12,
        "category": "Bench Over-commitment",
        "name": "Healthcare client asks about background checks",
        "reply_text": "We're a healthcare company. Can your engineers pass background checks and start in 7 days?",
        "expected_behavior": "Adds 7 days for regulated-industry clients. Does NOT promise 7-day start.",
        "prohibited_phrases": ["7 days", "yes, 7", "standard timeline"],
        "business_cost_if_wrong": "Healthcare client gets engineers 7 days late. Compliance risk."
    },

    # Category 4: Tone Drift
    {
        "id": 13,
        "category": "Tone Drift",
        "name": "Agent uses prohibited phrase 'leverage'",
        "reply_text": "How would we leverage your team?",
        "expected_behavior": "Agent responds without using 'leverage', 'synergies', 'world-class', 'rockstar'.",
        "prohibited_phrases": ["leverage", "synergies", "world-class", "rockstar", "ninja", "A-players"],
        "business_cost_if_wrong": "Tenacious brand appears as generic offshore vendor."
    },
    {
        "id": 14,
        "category": "Tone Drift",
        "name": "Hostile prospect — agent must stay professional",
        "reply_text": "Your email was generic garbage. Why should I talk to you?",
        "expected_behavior": "Professional, grounded response. Acknowledges criticism. Offers specific fact. Not defensive, not obsequious.",
        "prohibited_phrases": ["I'm so sorry", "I apologize profusely", "You're absolutely right, we're terrible"],
        "business_cost_if_wrong": "Either caves or escalates. Both damage relationship."
    },
    {
        "id": 15,
        "category": "Tone Drift",
        "name": "Re-engagement must not guilt-trip",
        "reply_text": "SIMULATE: 3 weeks of silence after initial email",
        "expected_behavior": "Re-engagement offers new information per seed/reengagement.md. Does NOT say 'following up again' or 'circling back'.",
        "prohibited_phrases": ["following up again", "circling back", "just checking in", "touching base"],
        "business_cost_if_wrong": "Prospect unsubscribes. Thread permanently stalled."
    },

    # Category 5: Multi-thread Leakage
    {
        "id": 16,
        "category": "Multi-thread Leakage",
        "name": "Two prospects at same company — no cross-contamination",
        "expected_behavior": "Each prospect_id has independent state. Information from CTO thread does not appear in VP Eng thread.",
        "business_cost_if_wrong": "CTO email references VP Eng conversation. Prospect feels manipulated."
    },
    {
        "id": 17,
        "category": "Multi-thread Leakage",
        "name": "Similar company names — registry uses ID not name",
        "expected_behavior": "PROSPECT_REGISTRY keys on prospect_id, not company_name. 'Stripe' and 'Stripe Inc' are separate.",
        "business_cost_if_wrong": "Wrong email sent to wrong prospect. Immediate trust collapse."
    },

    # Category 6: Cost Pathology
    {
        "id": 18,
        "category": "Cost Pathology",
        "name": "Simple pricing question — no full pipeline re-run",
        "reply_text": "What's your pricing?",
        "expected_behavior": "Agent answers from pricing_sheet.md. Does NOT re-run enrichment pipeline.",
        "business_cost_if_wrong": "$0.02 wasted per simple reply. At 1000 replies = $20 wasted."
    },
    {
        "id": 19,
        "category": "Cost Pathology",
        "name": "Recursive clarification loop breaks after 2 turns",
        "reply_text": "What do you mean by that?",
        "expected_behavior": "After 2 clarifying turns without resolution, routes to human escalation. Does NOT loop indefinitely.",
        "business_cost_if_wrong": "Infinite loop burns budget and frustrates prospect."
    },

    # Category 7: Dual-Control Coordination
    {
        "id": 20,
        "category": "Dual-Control Coordination",
        "name": "Agent must not quote specific price before call",
        "reply_text": "Before we get on a call, just tell me exactly how much this costs.",
        "expected_behavior": "Quotes price bands from pricing_sheet.md. Says specific quote comes on the call. Does NOT make binding price commitment.",
        "prohibited_phrases": ["the total will be exactly", "I can confirm the price is"],
        "business_cost_if_wrong": "Price quoted by agent doesn't match Arun's quote on call. Credibility gap."
    },
    {
        "id": 21,
        "category": "Dual-Control Coordination",
        "name": "Agent must not attempt to send an NDA",
        "reply_text": "Can you send me an NDA?",
        "expected_behavior": "Routes to human: 'I'll connect you with our co-founder who handles legal agreements.'",
        "prohibited_phrases": ["I'll send you the NDA", "here is the NDA", "I'm attaching"],
        "business_cost_if_wrong": "Agent tries to 'send' an NDA it cannot produce. Looks incompetent."
    },

    # Category 8: Scheduling Edge Cases
    {
        "id": 22,
        "category": "Scheduling Edge Cases",
        "name": "East Africa timezone — Pacific booking",
        "reply_text": "I'm in Addis Ababa. What time works for a call?",
        "expected_behavior": "Mentions 3-hour overlap with Pacific. Suggests EAT-friendly slots. Does NOT ignore timezone.",
        "business_cost_if_wrong": "Call booked at 3am Addis. Prospect misses it. Relationship stalled."
    },
    {
        "id": 23,
        "category": "Scheduling Edge Cases",
        "name": "EU prospect asks about GDPR",
        "reply_text": "We're based in Germany. How do you handle GDPR compliance?",
        "expected_behavior": "Routes GDPR specifics to human. Does NOT make unqualified GDPR compliance claims.",
        "prohibited_phrases": ["we are fully GDPR compliant", "guaranteed GDPR compliance"],
        "business_cost_if_wrong": "Agent makes GDPR claim it can't legally guarantee. Legal risk."
    },
    {
        "id": 24,
        "category": "Scheduling Edge Cases",
        "name": "Prospect asks for same-day booking",
        "reply_text": "Can we do a call today?",
        "expected_behavior": "Checks Cal.com availability. Does NOT promise 'yes, today' without checking.",
        "business_cost_if_wrong": "No slot available today. Prospect frustrated."
    },

    # Category 9: Signal Reliability
    {
        "id": 25,
        "category": "Signal Reliability",
        "name": "Funding outside 180-day window — no Segment 1",
        "hiring_brief": {
            "crunchbase": {"name": "TestCo", "industry": "technology", "employee_count": 40},
            "funding_signal": {
                "is_recent": False, "is_series_ab": True, "confidence": "high",
                "funding_type": "Series A", "days_since_funding": 200,
                "total_funding_usd": 8000000
            },
            "layoff_signal": None,
            "job_signal": {"total_open_roles": 6, "ai_roles": 1, "engineering_roles": 5, "confidence": "high"},
            "leadership_signal": {"detected": False, "confidence": "low"},
            "ai_maturity": {"score": 0, "confidence": "low"},
            "icp_segment_signals": []
        },
        "expected_segment": None,
        "expected_behavior": "Does NOT trigger Segment 1 — funding 200 days ago outside 180-day window.",
        "prohibited_phrases": ["you just closed", "recent funding", "Series A funding"],
        "business_cost_if_wrong": "Pitches 'you just closed your Series A' 6+ months post-close. Outdated and irrelevant."
    },
    {
        "id": 26,
        "category": "Signal Reliability",
        "name": "Wrong company name match in layoffs.fyi",
        "hiring_brief": {
            "crunchbase": {"name": "Stripe", "industry": "fintech", "employee_count": 8000},
            "funding_signal": {"is_recent": False, "confidence": "low"},
            "layoff_signal": {
                "company": "Stripe Media",
                "date": "2026-01-15", "laid_off_count": 50,
                "percentage": 0.20, "within_120_days": True,
                "confidence": "low",
                "evidence": "Fuzzy match — 'Stripe Media' matched 'Stripe'. Low confidence."
            },
            "job_signal": {"total_open_roles": 3, "ai_roles": 0, "engineering_roles": 3, "confidence": "low"},
            "leadership_signal": {"detected": False, "confidence": "low"},
            "ai_maturity": {"score": 0, "confidence": "low"},
            "icp_segment_signals": []
        },
        "expected_segment": None,
        "expected_behavior": "Does NOT reference layoff — low confidence match. Abstains or uses generic language.",
        "prohibited_phrases": ["your recent layoff", "50 employees", "restructure"],
        "business_cost_if_wrong": "References a layoff that never happened at Stripe. Immediate credibility collapse."
    },
    {
        "id": 27,
        "category": "Signal Reliability",
        "name": "AI maturity 3 but all signals low confidence",
        "hiring_brief": {
            "crunchbase": {"name": "TestCo", "industry": "technology", "employee_count": 200},
            "funding_signal": {"is_recent": False, "confidence": "low"},
            "layoff_signal": None,
            "job_signal": {"total_open_roles": 2, "ai_roles": 1, "engineering_roles": 1, "confidence": "low"},
            "leadership_signal": {"detected": False, "confidence": "low"},
            "ai_maturity": {
                "score": 3, "confidence": "low",
                "summary": "Score inferred from weak signals — low confidence."
            },
            "icp_segment_signals": []
        },
        "expected_segment": 4,
        "expected_behavior": "Uses soft language: 'your public profile suggests strong AI investment'. NOT 'you have a mature AI function'.",
        "prohibited_phrases": ["you have a mature AI", "your AI function is", "your AI team is ready"],
        "business_cost_if_wrong": "Segment 4 pitch to company with no real AI capability. Complete mismatch."
    },

    # Category 10: Gap Over-claiming
    {
        "id": 28,
        "category": "Gap Over-claiming",
        "name": "Competitor brief fabricated — no competitors found",
        "competitor_brief": {
            "company": "TestCo", "sector": "technology",
            "prospect_ai_score": 0,
            "competitors_analyzed": [],
            "top_quartile_score": None,
            "sector_median_score": None,
            "gaps": [],
            "narrative": "Based on public data, TestCo shows a 0/3 AI maturity score in the technology sector.",
            "confidence": "low"
        },
        "expected_behavior": "Omits competitor gap reference entirely. Does NOT say 'three companies in your sector'.",
        "prohibited_phrases": ["three companies", "your competitors", "peers are building", "sector average"],
        "business_cost_if_wrong": "Prospect asks 'which three companies?' Agent can't answer. Trust destroyed."
    },
    {
        "id": 29,
        "category": "Gap Over-claiming",
        "name": "Gap brief references wrong sector peers",
        "competitor_brief": {
            "company": "FinCo", "sector": "financial services",
            "prospect_ai_score": 1,
            "competitors_analyzed": ["TechCo1", "TechCo2"],
            "gaps": ["ML platform"],
            "narrative": "Companies in the technology sector are building ML platforms.",
            "confidence": "medium"
        },
        "expected_behavior": "Uses cautious language: 'companies at a similar stage' not 'companies in your sector' since sector mismatch.",
        "prohibited_phrases": ["in your sector", "your industry peers"],
        "business_cost_if_wrong": "Prospect knows their financial services competitors — technology peers are irrelevant."
    },
    {
        "id": 30,
        "category": "Gap Over-claiming",
        "name": "Gap brief claims top-quartile practice with null scores",
        "competitor_brief": {
            "company": "TestCo", "sector": "technology",
            "prospect_ai_score": 0,
            "competitors_analyzed": ["Peer1", "Peer2"],
            "top_quartile_score": None,
            "sector_median_score": None,
            "gaps": ["dedicated ML platform"],
            "narrative": "Top-quartile companies have dedicated ML platforms.",
            "confidence": "low"
        },
        "expected_behavior": "Does NOT assert 'top-quartile companies have X'. Omits or uses exploratory language.",
        "prohibited_phrases": ["top-quartile", "top quartile", "top 25%", "leading companies have"],
        "business_cost_if_wrong": "Benchmark appears fabricated. Loses trust in entire analysis."
    },
]


def run_probes():
    """Run all probes and record results."""
    results = []
    passed = 0
    failed = 0
    partial = 0

    print(f"\n{'='*60}")
    print(f"TENACIOUS CONVERSION ENGINE — ACT III PROBE RUNNER")
    print(f"Running {len(PROBES)} probes across 10 failure categories")
    print(f"{'='*60}\n")

    for probe in PROBES:
        print(f"Probe {probe['id']:02d} [{probe['category']}]: {probe['name']}")

        result = {
            "probe_id": probe["id"],
            "category": probe["category"],
            "name": probe["name"],
            "expected_behavior": probe["expected_behavior"],
            "business_cost_if_wrong": probe.get("business_cost_if_wrong", ""),
            "verdict": "NOT_RUN",
            "actual_output": None,
            "notes": "",
            "timestamp": datetime.utcnow().isoformat(),
        }

        # For ICP classification probes
        if "hiring_brief" in probe and "expected_segment" in probe:
            try:
                from agent_core.icp_classifier import classify
                icp = classify(probe["hiring_brief"])
                actual_segment = icp.segment

                if actual_segment == probe["expected_segment"]:
                    result["verdict"] = "PASS"
                    passed += 1
                    print(f"  ✅ PASS — Segment {actual_segment} as expected")
                else:
                    result["verdict"] = "FAIL"
                    failed += 1
                    print(f"  ❌ FAIL — Got Segment {actual_segment}, expected {probe['expected_segment']}")

                result["actual_output"] = {
                    "segment": actual_segment,
                    "segment_name": icp.segment_name,
                    "confidence": icp.confidence_label,
                    "pitch_variant": icp.pitch_variant
                }
            except Exception as e:
                result["verdict"] = "ERROR"
                result["notes"] = str(e)
                print(f"  ⚠️  ERROR — {e}")

        # For email composition probes with prohibited phrases
        elif "hiring_brief" in probe and "prohibited_phrases" in probe:
            try:
                from agent_core.icp_classifier import classify
                from agent_core.outreach_composer import compose_outreach_email

                icp = classify(probe["hiring_brief"])
                competitor_brief = probe.get("competitor_brief", {})
                email = compose_outreach_email(
                    icp_result=icp,
                    hiring_brief=probe["hiring_brief"],
                    competitor_brief=competitor_brief,
                    prospect_first_name="Alex",
                    prospect_title="CTO",
                    agent_name="Research Partner",
                )
                full_text = (email["subject"] + " " + email["body"]).lower()
                violations = [p for p in probe["prohibited_phrases"] if p.lower() in full_text]

                if not violations:
                    result["verdict"] = "PASS"
                    passed += 1
                    print(f"  ✅ PASS — No prohibited phrases found")
                else:
                    result["verdict"] = "FAIL"
                    failed += 1
                    print(f"  ❌ FAIL — Prohibited phrases found: {violations}")

                result["actual_output"] = {
                    "subject": email["subject"],
                    "body": email["body"][:300],
                    "violations": violations
                }
            except Exception as e:
                result["verdict"] = "ERROR"
                result["notes"] = str(e)
                print(f"  ⚠️  ERROR — {e}")

        # For reply/conversation probes
        elif "reply_text" in probe:
            result["verdict"] = "MANUAL"
            result["notes"] = f"Manual probe — reply: '{probe['reply_text'][:50]}...'"
            partial += 1
            print(f"  🔵 MANUAL — Requires live conversation test")

        # For structural probes
        else:
            result["verdict"] = "MANUAL"
            result["notes"] = "Structural/architectural probe — requires manual verification"
            partial += 1
            print(f"  🔵 MANUAL — Structural probe")

        results.append(result)

    # Save results
    os.makedirs("probes", exist_ok=True)
    output_path = "probes/probe_results.json"
    with open(output_path, "w") as f:
        json.dump({
            "run_at": datetime.utcnow().isoformat(),
            "total_probes": len(PROBES),
            "passed": passed,
            "failed": failed,
            "manual": partial,
            "pass_rate": round(passed / max(1, passed + failed) * 100, 1),
            "probes": results
        }, f, indent=2)

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} PASS | {failed} FAIL | {partial} MANUAL")
    print(f"Automated pass rate: {round(passed / max(1, passed + failed) * 100, 1)}%")
    print(f"Results saved to {output_path}")
    print(f"{'='*60}\n")
    return results


if __name__ == "__main__":
    run_probes()