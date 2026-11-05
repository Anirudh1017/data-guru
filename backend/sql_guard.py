"""Safety layer for LLM-generated SQL.

An LLM may only ever produce a single read-only SELECT over `mandi_prices`.
Everything else is rejected before it reaches SQLite, and the query still runs on a
read-only connection with a step budget, so a bad generation cannot modify data or hang
the server.
"""
import re
import sqlite3
import time
from pathlib import Path
from db import DB_PATH

ALLOWED_TABLES = {"mandi_prices"}
MAX_LIMIT = 200
STEP_BUDGET = 2_000_000
TIME_BUDGET_SECONDS = 5.0

FORBIDDEN = (
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "attach", "detach", "pragma", "vacuum", "reindex", "trigger",
    "grant", "revoke", "load_extension", "transaction", "commit", "rollback",
)

_STRING_LITERAL = re.compile(r"'(?:''|[^'])*'")
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_FROM_OR_JOIN = re.compile(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


class UnsafeSQLError(ValueError):
    pass


def _strip_literals(sql: str) -> str:
    return _STRING_LITERAL.sub("''", sql)


def validate_sql(raw: str) -> str:
    """Return a cleaned, safe SELECT statement or raise UnsafeSQLError."""
    if not raw or not raw.strip():
        raise UnsafeSQLError("Empty SQL")

    if _LINE_COMMENT.search(raw) or _BLOCK_COMMENT.search(raw):
        raise UnsafeSQLError("SQL comments are not allowed")

    sql = raw.strip()

    # Reject stacked statements: one optional trailing semicolon only.
    parts = [p for p in sql.split(";") if p.strip()]
    if len(parts) > 1:
        raise UnsafeSQLError("Multiple statements are not allowed")
    sql = parts[0].strip().rstrip(";").strip()

    if not re.match(r"^(select|with)\b", sql, re.IGNORECASE):
        raise UnsafeSQLError("Only SELECT queries are allowed")

    bare = _strip_literals(sql).lower()
    for word in FORBIDDEN:
        if re.search(rf"\b{word}\b", bare):
            raise UnsafeSQLError(f"Forbidden keyword: {word}")

    tables = {t.lower() for t in _FROM_OR_JOIN.findall(bare)}
    unknown = tables - ALLOWED_TABLES
    if unknown:
        raise UnsafeSQLError(f"Table not allowed: {', '.join(sorted(unknown))}")

    if not re.search(r"\blimit\s+\d+", bare):
        sql = f"{sql} LIMIT {MAX_LIMIT}"
    else:
        # Clamp an excessive LIMIT.
        def _clamp(m):
            n = int(m.group(1))
            return f"LIMIT {min(n, MAX_LIMIT)}"
        sql = re.sub(r"\blimit\s+(\d+)", _clamp, sql, flags=re.IGNORECASE)

    return sql


def execute_readonly(sql: str) -> dict:
    """Run validated SQL on a read-only connection and return columns + rows."""
    safe = validate_sql(sql)
    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    steps = {"n": 0}

    conn = sqlite3.connect(f"file:{Path(DB_PATH).as_posix()}?mode=ro", uri=True, timeout=3)

    def _guard():
        steps["n"] += 1
        if steps["n"] > STEP_BUDGET or time.monotonic() > deadline:
            return 1
        return 0

    try:
        conn.set_progress_handler(_guard, 10_000)
        cur = conn.execute(safe)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = [list(r) for r in cur.fetchmany(MAX_LIMIT)]
    except sqlite3.Error as exc:
        raise UnsafeSQLError(f"SQL failed: {exc}") from exc
    finally:
        conn.close()

    return {"sql": safe, "columns": columns, "rows": rows, "count": len(rows)}
