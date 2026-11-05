"""Load any AGMARKNET / data.gov.in CSV into SQLite.

Usage:
    python load_data.py path/to/file.csv
    python load_data.py path/to/file.csv --append   # keep other dates
"""
import sys
from pathlib import Path

import pandas as pd

from ingest import normalize_frame, upsert
from db import get_conn, init_db

BACKEND = Path(__file__).parent


def load(csv_path: str, append: bool = False) -> dict:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    print(f"Read {len(df)} rows from {csv_path}")
    print(f"Columns: {list(df.columns)}")

    clean = normalize_frame(df)
    if clean.empty:
        raise SystemExit("No usable rows after cleaning — check the date and price columns.")

    if not append:
        init_db()
        with get_conn() as conn:
            conn.execute("DELETE FROM mandi_prices")
            conn.commit()

    stats = upsert(clean)
    print(f"Inserted {stats['inserted']} rows for {len(stats['dates'])} date(s).")
    print(f"Database now holds {stats['total']} rows, latest {stats['latest_date']}.")
    return stats


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    csv = args[0] if args else str(BACKEND / "sample.csv")
    if not Path(csv).exists():
        print(f"No file at {csv}. Run seed_data.py for demo data.")
        sys.exit(1)
    load(csv, append="--append" in sys.argv)
