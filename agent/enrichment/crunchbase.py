"""
agent/enrichment/crunchbase.py
Crunchbase ODM sample lookup.

The CSV uses an 'industries' column with JSON arrays like:
  '[{"id": "software", "value": "Software"}, {"id": "analytics", "value": "Analytics"}]'

get_all_companies_in_sector() now parses that JSON instead of doing a
naive string-contains match on the raw column, which always returned empty.
"""
import os
import re
import json
from pathlib import Path
from typing import Optional
import pandas as pd
from functools import lru_cache

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "crunchbase_sample.csv"

# Map of common sector aliases to Crunchbase industry value keywords
SECTOR_ALIASES = {
    "technology":           ["software", "information technology", "internet", "saas", "cloud"],
    "software":             ["software", "saas", "cloud computing"],
    "fintech":              ["fintech", "financial services", "payments", "banking"],
    "financial services":   ["financial services", "fintech", "payments", "banking", "insurance"],
    "healthcare":           ["healthcare", "health", "medical", "biotech", "pharma"],
    "ai":                   ["artificial intelligence", "machine learning", "deep learning"],
    "data":                 ["analytics", "big data", "data", "business intelligence"],
    "ecommerce":            ["e-commerce", "retail", "marketplace"],
    "edtech":               ["education", "edtech", "e-learning"],
    "cybersecurity":        ["cybersecurity", "security", "network security"],
    "logistics":            ["logistics", "supply chain", "transportation"],
    "media":                ["media", "content", "publishing", "advertising"],
    "real estate":          ["real estate", "proptech"],
    "energy":               ["energy", "cleantech", "renewable energy"],
    "manufacturing":        ["manufacturing", "industrial", "hardware"],
    "consulting":           ["consulting", "professional services", "management consulting"],
}


@lru_cache(maxsize=1)
def _load_df() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Crunchbase sample not found at {DATA_PATH}. "
            "Download from https://github.com/luminati-io/Crunchbase-dataset-samples"
        )
    df = pd.read_csv(DATA_PATH, low_memory=False)
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
    return df


def _parse_industries(raw_value) -> list[str]:
    """Parse the JSON industries column into a flat list of lowercase value strings."""
    if not raw_value or (isinstance(raw_value, float)):
        return []
    try:
        items = json.loads(str(raw_value))
        return [item.get("value", "").lower() for item in items if isinstance(item, dict)]
    except (json.JSONDecodeError, TypeError):
        # Fallback: treat raw string as a plain comma-separated list
        return [s.strip().lower() for s in str(raw_value).split(",") if s.strip()]


def _sector_keywords(sector: str) -> list[str]:
    """Return the list of industry keywords to match for a given sector string."""
    sector_lower = sector.lower().strip()
    # Check alias table first
    for alias, keywords in SECTOR_ALIASES.items():
        if sector_lower == alias or sector_lower in keywords:
            return keywords
    # Fall back to exact match on the sector string itself
    return [sector_lower]


def lookup_company(name: str) -> Optional[dict]:
    df = _load_df()
    name_lower = name.lower().strip()
    mask = df["name"].str.lower().str.strip() == name_lower
    rows = df[mask]
    if rows.empty:
        mask = df["name"].str.lower().str.contains(re.escape(name_lower), na=False)
        rows = df[mask]
    if rows.empty:
        return None
    return _normalise(rows.iloc[0].to_dict())


def lookup_by_domain(domain: str) -> Optional[dict]:
    df = _load_df()
    domain_lower = domain.lower().strip().lstrip("www.")
    for col in ["homepage_url", "website", "domain"]:
        if col in df.columns:
            mask = df[col].str.lower().str.contains(domain_lower, na=False)
            rows = df[mask]
            if not rows.empty:
                return _normalise(rows.iloc[0].to_dict())
    return None


def _normalise(row: dict) -> dict:
    def _get(*keys):
        for k in keys:
            v = row.get(k)
            if v is not None and str(v).strip() not in ("", "nan", "None"):
                return v
        return None

    # Parse industries JSON into a readable string for the description field
    raw_industries = row.get("industries", "")
    industry_list = _parse_industries(raw_industries)
    industry_str = ", ".join(i.title() for i in industry_list) if industry_list else None

    # Parse about/full_description
    description = _get("about", "short_description", "full_description", "description")

    # Parse funding from funding_rounds_list if total_funding_usd missing
    total_funding = _get("funds_total", "total_funding_usd", "funding_total_usd")

    # Parse employee count
    employee_count = _get("num_employees", "employee_count", "num_employees_enum")

    return {
        "crunchbase_id":     _get("uuid", "id", "url"),
        "name":              _get("name", "company_name"),
        "description":       description,
        "homepage_url":      _get("website", "homepage_url"),
        "country":           _get("country_code", "country"),
        "city":              _get("city"),
        "employee_count":    employee_count,
        "founded_year":      _get("founded_date", "founded_on", "founded_year"),
        "total_funding_usd": total_funding,
        "last_funding_type": _get("last_funding_type"),
        "last_funding_at":   _get("last_funding_at", "last_funding_on"),
        "industry":          industry_str,
        "industries_raw":    industry_list,      # list of strings for sector matching
        "status":            _get("operating_status", "status"),
        "crunchbase_url":    _get("url", "cb_url", "crunchbase_url"),
    }


def get_all_companies_in_sector(sector: str, limit: int = 50) -> list[dict]:
    """
    Return up to `limit` companies whose industries list contains any keyword
    matching the given sector string.

    Uses JSON-aware parsing of the 'industries' column — the naive string-contains
    approach failed because the column stores JSON, not plain text.
    """
    df = _load_df()
    keywords = _sector_keywords(sector)

    if "industries" not in df.columns:
        return []

    def _matches(raw_value) -> bool:
        industry_values = _parse_industries(raw_value)
        for ind in industry_values:
            for kw in keywords:
                if kw in ind:
                    return True
        return False

    mask = df["industries"].apply(_matches)
    matched = df[mask].head(limit)

    if matched.empty:
        # Second pass: looser match — any keyword anywhere in the raw string
        raw_mask = df["industries"].str.lower().str.contains(
            "|".join(re.escape(kw) for kw in keywords), na=False
        )
        matched = df[raw_mask].head(limit)

    return [_normalise(r) for _, r in matched.iterrows()]