"""Deterministic demo dataset: 21 days of realistic AGMARKNET-style mandi prices.

Deterministic on purpose — every run produces the same numbers, so screenshots,
tests and trend answers stay stable. Replace with real data via fetch_daily.py.
"""
import hashlib
import math
from datetime import date, timedelta

from db import get_conn, init_db
from ingest import normalize_frame, upsert
import pandas as pd

END_DATE = date(2026, 11, 4)
DAYS = 21

# (state, district, market, commodity, variety, base modal price ₹/quintal)
MARKETS = [
    ("Tamil Nadu", "Chennai", "Koyambedu", "Tomato", "Desi", 1820),
    ("Tamil Nadu", "Chennai", "Parry's Corner", "Tomato", "Desi", 1980),
    ("Tamil Nadu", "Madurai", "Mattuthavani", "Tomato", "Desi", 1510),
    ("Tamil Nadu", "Coimbatore", "Gandhipuram", "Tomato", "Hybrid", 1620),
    ("Tamil Nadu", "Salem", "Salem Market", "Tomato", "Desi", 1330),
    ("Tamil Nadu", "Trichy", "Trichy Market", "Tomato", "Desi", 1450),
    ("Kerala", "Thiruvananthapuram", "Chalai", "Tomato", "Desi", 2210),
    ("Kerala", "Kochi", "Broadway", "Tomato", "Hybrid", 2090),
    ("Kerala", "Kozhikode", "Valiyangadi", "Tomato", "Desi", 2300),
    ("Karnataka", "Bengaluru", "K.R. Market", "Tomato", "Desi", 1420),
    ("Karnataka", "Mysuru", "Devaraja", "Tomato", "Desi", 1490),
    ("Andhra Pradesh", "Chittoor", "Chittoor Market", "Tomato", "Desi", 1210),
    ("Maharashtra", "Pune", "Gultekdi", "Tomato", "Desi", 1460),
    ("Delhi", "Delhi", "Azadpur", "Tomato", "Desi", 1910),
    ("West Bengal", "Kolkata", "Mechua", "Tomato", "Desi", 1720),

    ("Tamil Nadu", "Chennai", "Koyambedu", "Onion", "Small", 2810),
    ("Tamil Nadu", "Madurai", "Mattuthavani", "Onion", "Medium", 2610),
    ("Tamil Nadu", "Coimbatore", "Gandhipuram", "Onion", "Big", 2920),
    ("Tamil Nadu", "Salem", "Salem Market", "Onion", "Small", 2310),
    ("Tamil Nadu", "Trichy", "Trichy Market", "Onion", "Medium", 2710),
    ("Kerala", "Kochi", "Broadway", "Onion", "Medium", 3050),
    ("Kerala", "Thiruvananthapuram", "Chalai", "Onion", "Small", 3180),
    ("Karnataka", "Bengaluru", "K.R. Market", "Onion", "Small", 2620),
    ("Maharashtra", "Mumbai", "Vashi", "Onion", "Big", 2790),
    ("Maharashtra", "Nashik", "Nashik Market", "Onion", "Medium", 2480),
    ("Gujarat", "Ahmedabad", "Jamalpur", "Onion", "Medium", 2390),
    ("Rajasthan", "Jaipur", "Muhana", "Onion", "Small", 2250),
    ("Delhi", "Delhi", "Azadpur", "Onion", "Medium", 2720),
    ("West Bengal", "Kolkata", "Mechua", "Onion", "Small", 2880),

    ("Tamil Nadu", "Chennai", "Koyambedu", "Potato", "Chipsona", 2010),
    ("Tamil Nadu", "Madurai", "Mattuthavani", "Potato", "Chipsona", 1880),
    ("Kerala", "Kochi", "Broadway", "Potato", "Chipsona", 1810),
    ("Kerala", "Thiruvananthapuram", "Chalai", "Potato", "Chipsona", 1720),
    ("Karnataka", "Bengaluru", "K.R. Market", "Potato", "Chipsona", 1690),
    ("Punjab", "Jalandhar", "Jalandhar Market", "Potato", "Chipsona", 1180),
    ("Uttar Pradesh", "Agra", "Agra Market", "Potato", "Chipsona", 1310),
    ("West Bengal", "Kolkata", "Mechua", "Potato", "Chipsona", 1620),
    ("Delhi", "Delhi", "Azadpur", "Potato", "Chipsona", 1900),

    ("Punjab", "Ludhiana", "Ludhiana Market", "Wheat", "Dara", 2275),
    ("Madhya Pradesh", "Indore", "Indore Market", "Wheat", "Lokwan", 2410),
    ("West Bengal", "Kolkata", "Mechua", "Rice", "Common", 2650),
    ("Andhra Pradesh", "Guntur", "Guntur Market", "Rice", "Common", 2480),
    ("Tamil Nadu", "Theni", "Theni Market", "Banana", "Robusta", 1750),
    ("Maharashtra", "Jalgaon", "Jalgaon Market", "Banana", "Robusta", 1620),
]


def _noise(key: str) -> float:
    digest = hashlib.md5(key.encode()).hexdigest()
    return (int(digest[:8], 16) / 0xFFFFFFFF) * 2 - 1  # -1..1, deterministic


def build_rows() -> pd.DataFrame:
    rows = []
    for state, district, market, commodity, variety, base in MARKETS:
        phase = _noise(f"{market}{commodity}") * math.pi
        for i in range(DAYS):
            day = END_DATE - timedelta(days=DAYS - 1 - i)
            swing = math.sin(i / 3.2 + phase) * 0.07 + _noise(f"{market}{commodity}{day}") * 0.015
            modal = max(200, round(base * (1 + swing)))
            rows.append({
                "state": state, "district": district, "market": market,
                "commodity": commodity, "variety": variety,
                "arrival_date": day.isoformat(),
                "min_price": round(modal * 0.82),
                "max_price": round(modal * 1.18),
                "modal_price": modal,
            })
    return pd.DataFrame(rows)


def seed() -> dict:
    init_db()
    with get_conn() as conn:
        conn.execute("DELETE FROM mandi_prices")
        conn.commit()

    df = normalize_frame(build_rows())
    stats = upsert(df)
    print(
        f"Seeded {stats['inserted']:,} rows across {len(stats['dates'])} days "
        f"({stats['dates'][0]} -> {stats['dates'][-1]})."
    )
    print(f"Commodities: Tomato, Onion, Potato, Wheat, Rice, Banana")
    return stats


if __name__ == "__main__":
    seed()
