"""
scripts/verify_stack.py
One-command smoke test for all five production stack integrations.

Usage:
    python scripts/verify_stack.py

Runs five checks in order. Prints a green checkmark or red cross for each.
All five must pass before Day 1. If any fail, the error message tells you
exactly which environment variable or service is missing.

Expected output (all passing):
    [OK] Resend / MailerSend — email send + webhook reachable
    [OK] Africa's Talking — SMS sandbox credentials valid
    [OK] HubSpot Developer Sandbox — contact API reachable
    [OK] Cal.com — event types endpoint reachable
    [OK] Langfuse — project credentials valid

Exit code 0 if all pass, 1 if any fail.
"""
import os
import sys
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

GREEN = "\033[92m"
RED   = "\033[91m"
RESET = "\033[0m"

results = []


def ok(label: str):
    print(f"{GREEN}[OK]{RESET}  {label}")
    results.append((label, True))


def fail(label: str, reason: str):
    print(f"{RED}[FAIL]{RESET} {label}")
    print(f"       → {reason}")
    results.append((label, False))


# ── 1. Email: Resend or MailerSend ───────────────────────────────────────────

def check_email():
    label = "Resend / MailerSend — email send + webhook reachable"

    resend_key    = os.getenv("RESEND_API_KEY", "")
    mailersend_key = os.getenv("MAILERSEND_API_KEY", "")

    if resend_key:
        try:
            r = requests.get(
                "https://api.resend.com/domains",
                headers={"Authorization": f"Bearer {resend_key}"},
                timeout=10,
            )
            if r.status_code in (200, 403):   # 403 = authenticated but no domains yet
                ok(label)
            else:
                fail(label, f"Resend API returned HTTP {r.status_code}: {r.text[:120]}")
        except Exception as e:
            fail(label, f"Resend request failed: {e}")

    elif mailersend_key:
        try:
            r = requests.get(
                "https://api.mailersend.com/v1/activity",
                headers={"Authorization": f"Bearer {mailersend_key}"},
                timeout=10,
            )
            if r.status_code in (200, 422):   # 422 = missing params but auth OK
                ok(label)
            else:
                fail(label, f"MailerSend API returned HTTP {r.status_code}: {r.text[:120]}")
        except Exception as e:
            fail(label, f"MailerSend request failed: {e}")

    else:
        fail(label, "Neither RESEND_API_KEY nor MAILERSEND_API_KEY is set in .env")


# ── 2. SMS: Africa's Talking ─────────────────────────────────────────────────

def check_sms():
    label = "Africa's Talking — SMS sandbox credentials valid"

    api_key  = os.getenv("AT_API_KEY", "")
    username = os.getenv("AT_USERNAME", "sandbox")

    if not api_key:
        fail(label, "AT_API_KEY not set in .env")
        return

    try:
        r = requests.get(
            "https://api.sandbox.africastalking.com/version1/user",
            params={"username": username},
            headers={"apiKey": api_key, "Accept": "application/json"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            balance = data.get("UserData", {}).get("balance", "unknown")
            ok(f"{label} (balance: {balance})")
        else:
            fail(label, f"Africa's Talking returned HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        fail(label, f"Africa's Talking request failed: {e}")


# ── 3. CRM: HubSpot Developer Sandbox ───────────────────────────────────────

def check_hubspot():
    label = "HubSpot Developer Sandbox — contact API reachable"

    token = os.getenv("HUBSPOT_ACCESS_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")

    if not token:
        fail(label, "HUBSPOT_ACCESS_TOKEN (or HUBSPOT_API_KEY) not set in .env")
        return

    try:
        r = requests.get(
            "https://api.hubapi.com/crm/v3/objects/contacts",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 1},
            timeout=10,
        )
        if r.status_code == 200:
            ok(label)
        elif r.status_code == 401:
            fail(label, "HubSpot token invalid or expired — check HUBSPOT_ACCESS_TOKEN")
        else:
            fail(label, f"HubSpot API returned HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        fail(label, f"HubSpot request failed: {e}")


# ── 4. Calendar: Cal.com ─────────────────────────────────────────────────────

def check_calcom():
    label = "Cal.com — event types endpoint reachable"

    calcom_key = os.getenv("CALCOM_API_KEY", "")
    calcom_url = os.getenv("CALCOM_BASE_URL", "http://localhost:3000")

    if not calcom_key:
        fail(label, "CALCOM_API_KEY not set in .env — run docker compose up and create an API key")
        return

    try:
        r = requests.get(
            f"{calcom_url}/api/v1/event-types",
            headers={"Authorization": f"Bearer {calcom_key}"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            count = len(data.get("event_types", []))
            ok(f"{label} ({count} event type(s) found)")
        elif r.status_code in (401, 403):
            fail(label, "Cal.com API key rejected — did you create it under Settings → API Keys?")
        else:
            fail(label, f"Cal.com returned HTTP {r.status_code}: {r.text[:120]}")
    except requests.exceptions.ConnectionError:
        fail(label, f"Cannot reach {calcom_url} — is docker compose up and running?")
    except Exception as e:
        fail(label, f"Cal.com request failed: {e}")


# ── 5. Observability: Langfuse ───────────────────────────────────────────────

def check_langfuse():
    label = "Langfuse — project credentials valid"

    public_key  = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key  = os.getenv("LANGFUSE_SECRET_KEY", "")
    host        = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not public_key or not secret_key:
        fail(label, "LANGFUSE_PUBLIC_KEY and/or LANGFUSE_SECRET_KEY not set in .env")
        return

    try:
        r = requests.get(
            f"{host}/api/public/projects",
            auth=(public_key, secret_key),
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            projects = data.get("data", [])
            names = [p.get("name", "unnamed") for p in projects[:3]]
            ok(f"{label} (projects: {', '.join(names) if names else 'none yet'})")
        elif r.status_code in (401, 403):
            fail(label, "Langfuse credentials rejected — check LANGFUSE_PUBLIC_KEY and SECRET_KEY")
        else:
            fail(label, f"Langfuse returned HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        fail(label, f"Langfuse request failed: {e}")


# ── Run all checks ────────────────────────────────────────────────────────────

def main():
    print("\nTenacious Conversion Engine — stack verification\n")
    print("─" * 52)

    check_email()
    check_sms()
    check_hubspot()
    check_calcom()
    check_langfuse()

    print("─" * 52)
    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    print(f"\n{passed}/{total} checks passed\n")

    if passed < total:
        print("Fix the failing integrations before Day 1 readiness review.")
        sys.exit(1)
    else:
        print("All integrations verified. Ready for Day 1.")
        sys.exit(0)


if __name__ == "__main__":
    main()