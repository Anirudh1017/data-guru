"""Shared CSV/API normalisation and database writes."""
import re

import pandas as pd
from db import get_conn, init_db

CANONICAL = ["state", "district", "market", "commodity", "variety",
             "arrival_date", "min_price", "max_price", "modal_price"]

ALIASES = {
    "state": ["state", "state_name", "State"],
    "district": ["district", "district_name", "District"],
    "market": ["market", "market_name", "Market", "Market Name"],
    "commodity": ["commodity", "commodity_name", "Commodity"],
    "variety": ["variety", "Variety", "grade", "Grade"],
    "arrival_date": ["arrival_date", "Arrival Date", "date", "Date", "reported_date"],
    "min_price": ["min_price", "Min Price", "minimum_price", "Minimum Price"],
    "max_price": ["max_price", "Max Price", "maximum_price", "Maximum Price"],
    "modal_price": ["modal_price", "Modal Price", "modal", "Modal"],
}


def _pick(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    lower = {str(c).lower().strip(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _smart_case(value: str) -> str:
    """Fix ALL-CAPS source values without mangling 'K.R. Market' or "Parry's Corner"."""
    if not value or not any(ch.isalpha() for ch in value):
        return value
    if value != value.upper():
        return value
    lowered = value.lower()
    return re.sub(
        r"(^|[\s\-/])([a-z])",
        lambda m: m.group(1) + m.group(2).upper(),
        lowered,
    )


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Map arbitrary column names to the canonical schema and clean values."""
    out = pd.DataFrame()
    for target, candidates in ALIASES.items():
        src = _pick(df, candidates)
        if src is None:
            if target in ("state", "market", "commodity", "modal_price"):
                raise ValueError(f"Missing required column for '{target}'. Found: {list(df.columns)}")
            out[target] = ""
        else:
            out[target] = df[src].astype(str).str.strip()

    for col in ("state", "district", "market", "commodity", "variety"):
        out[col] = out[col].replace({"nan": "", "None": "", "NaN": ""}).map(_smart_case)

    raw_dates = out["arrival_date"].astype(str).str.strip()
    iso = pd.to_datetime(raw_dates, format="%Y-%m-%d", errors="coerce")
    loose = pd.to_datetime(raw_dates, dayfirst=True, errors="coerce", format="mixed")
    dates = iso.fillna(loose)
    out["arrival_date"] = dates.dt.strftime("%Y-%m-%d")
    out = out[out["arrival_date"].notna()]

    for col in ("min_price", "max_price", "modal_price"):
        cleaned = out[col].astype(str).str.replace(r"[₹,\s]", "", regex=True)
        out[col] = pd.to_numeric(cleaned, errors="coerce").fillna(0).astype(int)

    out = out[(out["market"] != "") & (out["commodity"] != "")]
    return out[CANONICAL].drop_duplicates()


def upsert(df: pd.DataFrame) -> dict:
    """Replace only the dates present in `df`, so older days survive a daily sync."""
    init_db()
    dates = sorted({d for d in df["arrival_date"].tolist() if d})
    records = df[CANONICAL].to_dict(orient="records")

    with get_conn() as conn:
        if dates:
            placeholders = ",".join("?" for _ in dates)
            conn.execute(f"DELETE FROM mandi_prices WHERE arrival_date IN ({placeholders})", dates)
        conn.executemany(
            "INSERT INTO mandi_prices (state,district,market,commodity,variety,"
            "arrival_date,min_price,max_price,modal_price) "
            "VALUES (:state,:district,:market,:commodity,:variety,"
            ":arrival_date,:min_price,:max_price,:modal_price)",
            records,
        )
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM mandi_prices").fetchone()[0]
        latest = conn.execute("SELECT MAX(arrival_date) FROM mandi_prices").fetchone()[0]

    return {"inserted": len(records), "dates": dates, "total": total, "latest_date": latest}
