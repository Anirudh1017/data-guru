"""Query builders for the rule-based path, plus the executor for LLM-generated SQL."""
from datetime import date

from db import get_conn
from sql_guard import execute_readonly

MAX_ROWS = 50


def _fmt_date(iso: str | None) -> str:
    """2026-11-04 -> 4 Nov 2026, for prose only."""
    if not iso:
        return ""
    try:
        return f"{date.fromisoformat(iso).day} {date.fromisoformat(iso).strftime('%b %Y')}"
    except ValueError:
        return iso


def _commodity_list(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT commodity FROM mandi_prices ORDER BY commodity")]


def _latest_date(conn):
    row = conn.execute("SELECT MAX(arrival_date) FROM mandi_prices").fetchone()
    return row[0] if row else None


def _infer_chart(columns: list[str]) -> str | None:
    lowered = [c.lower() for c in columns]
    if any("date" in c for c in lowered):
        return "line"
    has_numeric = any(k in c for c in lowered for k in ("price", "avg", "modal", "min", "max", "count", "markets"))
    has_label = any(k in c for c in lowered for k in ("market", "state", "district", "commodity"))
    if has_numeric and has_label:
        return "bar"
    return None


def _chart_payload(columns: list[str], rows: list[list]) -> list[dict]:
    """Pick label + value columns for the chart component."""
    if not columns or not rows:
        return []
    lowered = [c.lower() for c in columns]
    date_idx = next((i for i, c in enumerate(lowered) if "date" in c), None)
    label_idx = next((i for i, c in enumerate(lowered) if any(k in c for k in ("market", "state", "district", "commodity"))), None)
    value_idx = next((i for i, c in enumerate(lowered) if any(k in c for k in ("avg", "modal", "price"))), None)
    if value_idx is None:
        return []
    label = date_idx if date_idx is not None else label_idx
    if label is None:
        return []
    return [
        {"name": str(row[label]), "value": float(row[value_idx])}
        for row in rows
        if row[value_idx] is not None
    ]


def run_query(parsed: dict) -> dict:
    intent = parsed["intent"]
    commodity = parsed.get("commodity")
    states = parsed.get("states") or []
    districts = parsed.get("districts") or []
    markets = parsed.get("markets") or []

    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM mandi_prices").fetchone()[0]
        latest = _latest_date(conn)

        if int(total) == 0:
            return {
                "intent": intent,
                "answer": "No data loaded yet. Run seed_data.py or fetch_daily.py first.",
                "columns": [], "rows": [], "count": 0, "source_date": None, "sql_used": None,
            }

        avail_commodities = _commodity_list(conn)
        avail = ", ".join(avail_commodities)
        state_list = [r[0] for r in conn.execute("SELECT DISTINCT state FROM mandi_prices ORDER BY state")]

        if parsed.get("is_junk"):
            return {
                "intent": "invalid",
                "answer": (
                    f"We could not recognize a valid agricultural query in that input. "
                    f"This portal tracks Indian mandi prices for {avail} across {len(state_list)} states. "
                    f'Try asking: "Tomato", "What is the tomato price in Chennai?", or "Which market has the cheapest onion price?"'
                ),
                "columns": [], "rows": [], "count": 0, "source_date": latest, "sql_used": None,
                "supported_commodities": avail_commodities,
                "supported_states": state_list,
            }

        if not commodity:
            subj = parsed.get("unknown_subject")
            prefix = (
                f'"{subj}" is not an agricultural commodity tracked in this mandi database. '
                if subj
                else "No tracked commodity was found in your search. "
            )
            return {
                "intent": "out_of_scope" if subj else "unknown",
                "answer": (
                    f"{prefix}Available commodities: {avail} (across {len(state_list)} states). "
                    f'Try: "What is the tomato price in Chennai?" or "Which market has the cheapest onion price?"'
                ),
                "columns": [], "rows": [], "count": 0, "source_date": latest, "sql_used": None,
                "supported_commodities": avail_commodities,
                "supported_states": state_list,
            }
        # ---------- trend over time ----------
        if intent == "trend":
            cols = ["Date", "Avg Modal Price (₹/quintal)", "Records"]
            sql = (
                "SELECT arrival_date, CAST(ROUND(AVG(modal_price)) AS INTEGER), COUNT(*) "
                "FROM mandi_prices WHERE commodity=? "
            )
            params: list = [commodity]
            if states:
                sql += "AND state=? "
                params.append(states[0])
            sql += "GROUP BY arrival_date ORDER BY arrival_date ASC LIMIT 60"
            rows = conn.execute(sql, params).fetchall()
            if not rows:
                return {"intent": intent, "answer": f"No {commodity.lower()} history found.", "columns": cols,
                        "rows": [], "count": 0, "source_date": latest, "sql_used": sql}
            first, last = rows[0], rows[-1]
            direction = "up" if last[1] > first[1] else ("down" if last[1] < first[1] else "flat")
            scope = f" in {states[0]}" if states else ""
            answer = (
                f"Average modal {commodity.lower()} price{scope} has moved {direction} from "
                f"₹{first[1]:,} on {_fmt_date(first[0])} to ₹{last[1]:,} on {_fmt_date(last[0])}, "
                f"across {len(rows)} days."
            )
            return {"intent": intent, "answer": answer, "columns": cols, "rows": [list(r) for r in rows],
                    "count": len(rows), "source_date": latest, "sql_used": sql, "chart_type": "line",
                    "chart": _chart_payload(cols, [list(r) for r in rows])}

        # ---------- cheapest markets ----------
        if intent == "cheapest":
            cols = ["Market", "District", "State", "Modal Price (₹/quintal)"]
            sql = (
                "SELECT market, district, state, modal_price FROM mandi_prices "
                "WHERE commodity=? AND modal_price IS NOT NULL AND arrival_date=? "
            )
            params = [commodity, latest]
            if states:
                sql += "AND state=? "
                params.append(states[0])
            if districts:
                sql += "AND district=? "
                params.append(districts[0])
            sql += " ORDER BY modal_price ASC LIMIT 5"
            rows = conn.execute(sql, params).fetchall()
            if not rows:
                return {"intent": intent, "answer": f"No {commodity} records found{' in ' + states[0] if states else ''}.",
                        "columns": cols, "rows": [], "count": 0, "source_date": latest, "sql_used": sql}
            scope = f" in {states[0]}" if states else ""
            n = len(rows)
            answer = (
                f"Based on the latest records ({_fmt_date(latest)}), here {'is' if n == 1 else 'are'} "
                f"{n} market{'s' if n != 1 else ''} with the lowest reported modal "
                f"{commodity.lower()} prices{scope}."
            )
            out = [list(r) for r in rows]
            return {"intent": intent, "answer": answer, "columns": cols, "rows": out, "count": len(out),
                    "source_date": latest, "sql_used": sql, "chart_type": "bar", "chart": _chart_payload(cols, out)}

        # ---------- compare states ----------
        if intent == "compare":
            cols = ["State", "Avg Modal Price (₹/quintal)", "Markets Covered"]
            ph = ",".join("?" for _ in states)
            sql = (
                f"SELECT state, CAST(ROUND(AVG(modal_price)) AS INTEGER), COUNT(DISTINCT market) "
                f"FROM mandi_prices WHERE commodity=? AND state IN ({ph}) "
                f"GROUP BY state ORDER BY AVG(modal_price) ASC"
            )
            rows = conn.execute(sql, [commodity, *states]).fetchall()
            if not rows:
                return {"intent": intent, "answer": f"No {commodity} records found for comparison.",
                        "columns": cols, "rows": [], "count": 0, "source_date": latest, "sql_used": sql}
            cheapest = rows[0]
            answer = (
                f"{cheapest[0]} has the lowest average modal {commodity.lower()} price at "
                f"₹{cheapest[1]:,}/quintal among the states you asked about."
            )
            out = [list(r) for r in rows]
            return {"intent": intent, "answer": answer, "columns": cols, "rows": out, "count": len(out),
                    "source_date": latest, "sql_used": sql, "chart_type": "bar", "chart": _chart_payload(cols, out)}

        # ---------- price at a place ----------
        if intent == "price":
            cols = ["Market", "District", "State", "Variety", "Min (₹)", "Modal (₹)", "Max (₹)"]
            sql = (
                "SELECT market, district, state, variety, min_price, modal_price, max_price "
                "FROM mandi_prices WHERE commodity=? AND arrival_date=? "
            )
            params = [commodity, latest]
            if markets:
                sql += "AND market=? "
                params.append(markets[0])
            elif districts:
                sql += "AND district=? "
                params.append(districts[0])
            elif states:
                sql += "AND state=? "
                params.append(states[0])
            sql += "ORDER BY modal_price ASC LIMIT 12"
            rows = conn.execute(sql, params).fetchall()
            place = (markets or districts or states or [""])[0]
            if not rows:
                return {"intent": intent, "answer": f"No {commodity} price records found for {place}.",
                        "columns": cols, "rows": [], "count": 0, "source_date": latest, "sql_used": sql}
            answer = (
                f"Latest modal {commodity.lower()} price{' in ' + place if place else ''} is "
                f"₹{rows[0][5]:,}/quintal at {rows[0][0]} (as of {_fmt_date(latest)})."
            )
            out = [list(r) for r in rows]
            return {"intent": intent, "answer": answer, "columns": cols, "rows": out, "count": len(out),
                    "source_date": latest, "sql_used": sql}

        # ---------- browse ----------
        # ---------- browse (e.g. bare commodity name like "Tomato") ----------
        cols = ["Market", "District", "State", "Variety", "Modal Price (₹/quintal)"]
        sql = (
            "SELECT market, district, state, variety, modal_price FROM mandi_prices "
            "WHERE commodity=? AND arrival_date=? ORDER BY modal_price ASC LIMIT 15"
        )
        rows = conn.execute(sql, [commodity, latest]).fetchall()
        out = [list(r) for r in rows]
        if out:
            low_m, _, low_s, _, low_p = out[0]
            high_m, _, high_s, _, high_p = out[-1]
            answer = (
                f"Showing {len(out)} {commodity.lower()} markets for {_fmt_date(latest)} — "
                f"modal prices range from ₹{low_p:,}/quintal at {low_m} ({low_s}) "
                f"to ₹{high_p:,}/quintal at {high_m} ({high_s})."
            )
        else:
            answer = f"No {commodity.lower()} records found for {_fmt_date(latest)}."
        return {
            "intent": intent,
            "answer": answer,
            "columns": cols,
            "rows": out,
            "count": len(out),
            "source_date": latest,
            "sql_used": sql,
            "chart_type": "bar",
            "chart": _chart_payload(cols, out[:10]),
        }

def run_generated_sql(sql: str, parsed: dict | None = None) -> dict:
    """Execute guarded LLM SQL and shape it like the rule-based responses."""
    result = execute_readonly(sql)
    columns, rows = result["columns"], result["rows"]
    latest = None
    avail_commodities: list[str] = []
    state_list: list[str] = []
    try:
        with get_conn() as conn:
            latest = _latest_date(conn)
            avail_commodities = _commodity_list(conn)
            state_list = [r[0] for r in conn.execute("SELECT DISTINCT state FROM mandi_prices ORDER BY state")]
    except Exception:
        pass

    count = len(rows)
    if count and columns:
        answer = f"Here {'is' if count == 1 else 'are'} {count} matching record{'s' if count != 1 else ''}."
    else:
        subj = (parsed or {}).get("unknown_subject")
        avail_str = ", ".join(avail_commodities)
        if subj:
            answer = (
                f'"{subj}" is not in the mandi dataset (0 matching records). '
                f"Available commodities: {avail_str} across {len(state_list)} states."
            )
        elif avail_str:
            answer = (
                f"No matching records found in the mandi database. "
                f"Available commodities: {avail_str} across {len(state_list)} states."
            )
        else:
            answer = "Found 0 matching records in the mandi database."

    chart_type = _infer_chart(columns) if count else None
    out: dict = {
        "intent": "llm_sql" if count else ("out_of_scope" if (parsed or {}).get("unknown_subject") else "llm_sql"),
        "answer": answer,
        "columns": columns if count else [],
        "rows": rows,
        "count": count,
        "source_date": latest,
        "sql_used": result["sql"],
        "chart_type": chart_type,
        "chart": _chart_payload(columns, rows) if chart_type else [],
    }
    if not count and avail_commodities:
        out["supported_commodities"] = avail_commodities
        out["supported_states"] = state_list
    return out
