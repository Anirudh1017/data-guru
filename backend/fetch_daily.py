"""Sync live mandi prices from data.gov.in into SQLite.

Needs a free API key (https://data.gov.in -> My Account -> API key):

    backend/.env:  DATA_GOV_API_KEY=579b464db66ec23bdd000001...

Usage:
    python fetch_daily.py                 # fetch everything, keep older dates
    python fetch_daily.py --max-pages 3   # quick test
    python fetch_daily.py --save raw.csv  # also write the raw rows
"""
import sys
import time
from pathlib import Path

import httpx
import pandas as pd

import settings
from ingest import normalize_frame, upsert

PAGE_SIZE = 1000
BACKEND = Path(__file__).parent


def fetch_page(offset: int, limit: int = PAGE_SIZE) -> dict:
    params = {
        "api-key": settings.DATA_GOV_API_KEY,
        "format": "json",
        "limit": limit,
        "offset": offset,
    }
    url = f"{settings.DATA_GOV_BASE}/{settings.DATA_GOV_RESOURCE}"
    with httpx.Client(timeout=60) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def fetch_all(max_pages: int = 60) -> pd.DataFrame:
    if not settings.data_available():
        raise SystemExit(
            "DATA_GOV_API_KEY is not set.\n"
            "  1. Register at https://data.gov.in\n"
            "  2. Copy your API key into backend/.env\n"
            "  3. Re-run: python fetch_daily.py\n"
            "For demo data without a key: python seed_data.py"
        )

    records: list[dict] = []
    offset = 0
    total = None

    for page in range(max_pages):
        try:
            data = fetch_page(offset)
        except httpx.HTTPStatusError as exc:
            raise SystemExit(
                f"data.gov.in returned {exc.response.status_code}. "
                "Check that your API key is valid and not rate-limited."
            ) from exc
        except httpx.HTTPError as exc:
            raise SystemExit(f"Could not reach data.gov.in: {exc}") from exc

        if total is None:
            total = int(data.get("total", 0))
            print(f"Dataset reports {total:,} records")

        batch = data.get("records") or data.get("data") or []
        if not batch:
            break
        records.extend(batch)
        offset += len(batch)
        print(f"  fetched {offset:,}/{total:,}")

        if offset >= total:
            break
        time.sleep(0.4)  # be polite to the public API

    if not records:
        raise SystemExit("The API returned no records. Try again later.")
    return pd.DataFrame(records)


def sync(max_pages: int = 60, save: str | None = None) -> dict:
    raw = fetch_all(max_pages=max_pages)
    if save:
        path = BACKEND / save if not Path(save).is_absolute() else Path(save)
        raw.to_csv(path, index=False)
        print(f"Saved raw rows to {path}")

    clean = normalize_frame(raw)
    stats = upsert(clean)
    print(
        f"Synced {stats['inserted']:,} rows across {len(stats['dates'])} date(s). "
        f"Database total: {stats['total']:,}, latest {stats['latest_date']}."
    )
    return stats


if __name__ == "__main__":
    pages = 60
    save = None
    argv = sys.argv[1:]
    if "--max-pages" in argv:
        pages = int(argv[argv.index("--max-pages") + 1])
    if "--save" in argv:
        save = argv[argv.index("--save") + 1]
    sync(max_pages=pages, save=save)
