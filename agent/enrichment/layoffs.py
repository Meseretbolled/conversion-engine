import re
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
from functools import lru_cache
import pandas as pd

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "layoffs.csv"
LOOKBACK_DAYS = 120

@lru_cache(maxsize=1)
def _load_df() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"layoffs.fyi CSV not found at {DATA_PATH}. Download from https://layoffs.fyi")
    df = pd.read_csv(DATA_PATH, low_memory=False)
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
    date_col = next((c for c in df.columns if "date" in c), None)
    if date_col:
        df["_parsed_date"] = pd.to_datetime(df[date_col], errors="coerce")
    return df

def check_layoffs(company_name: str) -> Optional[dict]:
    try:
        df = _load_df()
    except FileNotFoundError:
        return None
    name_lower = company_name.lower().strip()
    company_col = next((c for c in df.columns if c in ("company", "company_name", "name")), None)
    if not company_col:
        return None
    mask = df[company_col].str.lower().str.contains(re.escape(name_lower), na=False)
    matches = df[mask].copy()
    if matches.empty:
        return None
    cutoff = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    if "_parsed_date" in matches.columns:
        recent = matches[matches["_parsed_date"] >= cutoff]
        if not recent.empty:
            matches = recent
    row = matches.sort_values("_parsed_date", ascending=False).iloc[0]
    def _get(*keys):
        for k in keys:
            v = row.get(k)
            if v is not None and str(v).strip() not in ("", "nan", "None"):
                return v
        return None
    return {
        "company":        _get(company_col),
        "date":           str(_get("_parsed_date", "date")),
        "laid_off_count": _get("laid_off", "num_laid_off", "total_laid_off"),
        "percentage":     _get("percentage_laid_off", "percentage"),
        "stage":          _get("stage"),
        "source":         _get("source", "sources"),
        "within_120_days": True,
    }
