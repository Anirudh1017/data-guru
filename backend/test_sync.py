"""Prove the data.gov.in sync path works, without a real API key."""
import io
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import db

db.DB_PATH = Path(tempfile.mkdtemp()) / "sync_test.db"

import fetch_daily
import ingest
import settings

failures = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  -> {detail}" if not condition else ""))
    if not condition:
        failures.append(name)


PAGES = {
    0: {
        "total": 3,
        "records": [
            {"state": "TAMIL NADU", "district": "CHENNAI", "market": "KOYAMBEDU",
             "commodity": "TOMATO", "variety": "DESI", "arrival_date": "04/11/2026",
             "min_price": "1200", "max_price": "2200", "modal_price": "1800"},
            {"state": "KERALA", "district": "KOCHI", "market": "PARRY'S CORNER",
             "commodity": "ONION", "variety": "MEDIUM", "arrival_date": "04/11/2026",
             "min_price": "2000", "max_price": "3000", "modal_price": "2600"},
        ],
    },
    2: {
        "total": 3,
        "records": [
            {"state": "PUNJAB", "district": "JALANDHAR", "market": "JALANDHAR MARKET",
             "commodity": "POTATO", "variety": "CHIPSONA", "arrival_date": "03/11/2026",
             "min_price": "1000", "max_price": "1400", "modal_price": "1180"},
        ],
    },
}

print("== sync without a key ==")
settings.DATA_GOV_API_KEY = ""
try:
    fetch_daily.fetch_all()
    check("no key raises", False, "did not raise")
except SystemExit as exc:
    check("no key raises clear message", "DATA_GOV_API_KEY" in str(exc), str(exc))

print("\n== mocked data.gov.in pages ==")
settings.DATA_GOV_API_KEY = "test-key"
fetch_daily.fetch_page = lambda offset, limit=1000: PAGES[offset]
raw = fetch_daily.fetch_all(max_pages=5)
check("paginates all records", len(raw) == 3, len(raw))

clean = ingest.normalize_frame(raw)
check("canonical columns", list(clean.columns) == ingest.CANONICAL, list(clean.columns))
check("DD/MM/YYYY parsed", set(clean["arrival_date"]) == {"2026-11-04", "2026-11-03"},
      list(clean["arrival_date"]))
check("uppercase title-cased", "Tamil Nadu" in set(clean["state"]), set(clean["state"]))
check("apostrophe preserved", "Parry's Corner" in set(clean["market"]), set(clean["market"]))
check("prices numeric", clean["modal_price"].tolist() == [1800, 2600, 1180], clean["modal_price"].tolist())

stats = ingest.upsert(clean)
check("inserted rows", stats["inserted"] == 3, stats)
check("db total", stats["total"] == 3, stats["total"])

stats2 = ingest.upsert(clean)
check("re-sync is idempotent", stats2["total"] == 3, stats2["total"])

print("\n" + ("ALL SYNC CHECKS PASS" if not failures else f"{len(failures)} FAILURES: {failures}"))
sys.exit(1 if failures else 0)
