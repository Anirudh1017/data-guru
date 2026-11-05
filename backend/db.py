import sqlite3
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
DB_PATH = Path(os.getenv("DB_PATH", str(BACKEND_DIR / "data_guru.db")))

SCHEMA = """
CREATE TABLE IF NOT EXISTS mandi_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    state TEXT NOT NULL,
    district TEXT,
    market TEXT NOT NULL,
    commodity TEXT NOT NULL,
    variety TEXT,
    arrival_date TEXT,
    min_price INTEGER,
    max_price INTEGER,
    modal_price INTEGER
);
CREATE INDEX IF NOT EXISTS idx_commodity ON mandi_prices(commodity);
CREATE INDEX IF NOT EXISTS idx_state ON mandi_prices(state);
CREATE INDEX IF NOT EXISTS idx_modal ON mandi_prices(modal_price);
"""

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
