import os, re
from pathlib import Path
from typing import Optional
import pandas as pd
from functools import lru_cache

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "crunchbase_sample.csv"

@lru_cache(maxsize=1)
def _load_df() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Crunchbase sample not found at {DATA_PATH}. Download from https://github.com/luminati-io/Crunchbase-dataset-samples")
    df = pd.read_csv(DATA_PATH, low_memory=False)
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
    return df

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
    return {
        "crunchbase_id":     _get("uuid", "id", "cb_url"),
        "name":              _get("name", "company_name"),
        "description":       _get("short_description", "description"),
        "homepage_url":      _get("homepage_url", "website"),
        "country":           _get("country_code", "country"),
        "city":              _get("city"),
        "employee_count":    _get("employee_count", "num_employees_enum"),
        "founded_year":      _get("founded_on", "founded_year"),
        "total_funding_usd": _get("total_funding_usd", "funding_total_usd"),
        "last_funding_type": _get("last_funding_type"),
        "last_funding_at":   _get("last_funding_at", "last_funding_on"),
        "industry":          _get("category_list", "industry"),
        "status":            _get("status"),
        "crunchbase_url":    _get("cb_url", "crunchbase_url"),
    }

def get_all_companies_in_sector(sector: str, limit: int = 50) -> list[dict]:
    df = _load_df()
    sector_lower = sector.lower()
    if "category_list" in df.columns:
        mask = df["category_list"].str.lower().str.contains(sector_lower, na=False)
    elif "industry" in df.columns:
        mask = df["industry"].str.lower().str.contains(sector_lower, na=False)
    else:
        return []
    return [_normalise(r) for _, r in df[mask].head(limit).iterrows()]
