"""
scripts/bulk_upsert_companies.py
Bulk upsert companies from Crunchbase CSV to HubSpot.

Usage:
    python scripts/bulk_upsert_companies.py

This script reads data/crunchbase_sample.csv and creates/updates company records in HubSpot.
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "agent"))

from crm.hubspot_mcp import upsert_company

def main():
    csv_path = BASE_DIR / "data" / "crunchbase_sample.csv"
    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}")
        return

    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

    print(f"Processing {len(df)} companies from {csv_path}")

    success_count = 0
    error_count = 0

    for idx, row in df.iterrows():
        name = row.get("name")
        if not name or str(name).strip() == "" or str(name).lower() == "nan":
            continue

        # Extract domain from website
        website = row.get("website", "")
        domain = ""
        if website and str(website).startswith("http"):
            from urllib.parse import urlparse
            domain = urlparse(str(website)).netloc.lstrip("www.")

        # Parse industries
        industries_raw = row.get("industries", "")
        industry = ""
        if industries_raw:
            try:
                import json
                items = json.loads(str(industries_raw))
                if isinstance(items, list) and items:
                    industry = items[0].get("value", "")
            except:
                pass

        description = row.get("about") or row.get("short_description") or ""

        country = row.get("country_code", "")
        city = row.get("city", "")

        employee_count = row.get("num_employees", "")
        if employee_count and str(employee_count).endswith("-"):
            employee_count = str(employee_count).split("-")[0]

        total_funding = row.get("funds_total") or row.get("total_funding_usd") or ""
        founded_year = str(row.get("founded_date", "")).split("-")[0] if row.get("founded_date") else ""

        crunchbase_id = row.get("uuid") or row.get("id") or ""

        result = upsert_company(
            name=str(name).strip(),
            domain=domain,
            industry=industry,
            description=str(description)[:500] if description else "",
            country=str(country),
            city=str(city),
            employee_count=str(employee_count),
            total_funding_usd=str(total_funding),
            founded_year=founded_year,
            crunchbase_id=str(crunchbase_id)
        )

        if result.get("error"):
            print(f"Error upserting {name}: {result['error']}")
            error_count += 1
        else:
            action = result.get("action", "unknown")
            print(f"{action.capitalize()} company: {name}")
            success_count += 1

        # Rate limit to avoid hitting HubSpot API limits
        time.sleep(0.1)

    print(f"\nCompleted: {success_count} successes, {error_count} errors")

if __name__ == "__main__":
    main()