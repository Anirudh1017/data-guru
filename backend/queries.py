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
    if has_numeric and (has_label or sum(1 for c in lowered if any(k in c for k in ("min", "modal", "max"))) >= 2):
        return "bar"
    return None


def _chart_payload(columns: list[str], rows: list[list]) -> list[dict]:
    """Pick label + value columns (or multi-series pivot) for the chart component."""
    if not columns or not rows:
        return []
    lowered = [c.lower() for c in columns]
    # When only 1 row is returned and it has Min / Modal / Max price columns, chart the Min/Modal/Max breakdown
    if len(rows) == 1:
        min_idx = next((i for i, c in enumerate(lowered) if "min" in c), None)
        mod_idx = next((i for i, c in enumerate(lowered) if "modal" in c), None)
        max_idx = next((i for i, c in enumerate(lowered) if "max" in c), None)
        if min_idx is not None and mod_idx is not None and max_idx is not None:
            r0 = rows[0]
            pts = []
            for lbl, idx in (("Min Price", min_idx), ("Modal Price", mod_idx), ("Max Price", max_idx)):
                if r0[idx] is not None:
                    pts.append({"name": lbl, "value": float(r0[idx])})
            if len(pts) >= 2:
                return pts

    date_idx = next((i for i, c in enumerate(lowered) if "date" in c), None)

    # Wide table where multiple numeric columns represent series across dates (e.g. Date | Tomato | Onion | Potato)
    if date_idx is not None and len(columns) >= 3:
        non_date_numeric = [
            i for i, c in enumerate(lowered)
            if i != date_idx and "record" not in c and "count" not in c
            and any(isinstance(r[i], (int, float)) for r in rows if r[i] is not None)
        ]
        if len(non_date_numeric) >= 2:
            pts = []
            for row in rows:
                first_val = next((float(row[i]) for i in non_date_numeric if row[i] is not None), 0.0)
                entry: dict = {"name": str(row[date_idx]), "value": first_val}
                for i in non_date_numeric:
                    if row[i] is not None:
                        entry[columns[i]] = float(row[i])
                pts.append(entry)
            return pts

    label_idx = next((i for i, c in enumerate(lowered) if any(k in c for k in ("market", "state", "district", "commodity"))), None)
    value_idx = next((i for i, c in enumerate(lowered) if any(k in c for k in ("avg", "modal", "price"))), None)
    if value_idx is None:
        return []

    # Multi-series date trend (e.g. Date + Commodity + Avg Modal Price)
    if date_idx is not None and label_idx is not None and label_idx != date_idx:
        by_date: dict[str, dict] = {}
        series_names: list[str] = []
        for row in rows:
            if row[value_idx] is None or row[date_idx] is None or row[label_idx] is None:
                continue
            d_str = str(row[date_idx])
            s_name = str(row[label_idx])
            val = float(row[value_idx])
            if s_name not in series_names:
                series_names.append(s_name)
            if d_str not in by_date:
                by_date[d_str] = {"name": d_str, "value": val}
            by_date[d_str][s_name] = val
        if len(series_names) >= 2 and len(by_date) >= 2:
            return [by_date[k] for k in sorted(by_date.keys())]
    label = date_idx if date_idx is not None else label_idx
    if label is None:
        return []
    return [
        {"name": str(row[label]), "value": float(row[value_idx])}
        for row in rows
        if row[value_idx] is not None
    ]


def apply_unit_conversion(result: dict, parsed: dict | None) -> dict:
    """Enforce wholesale quintal-only pricing when Kg or gms units are requested."""
    if not parsed:
        return result
    req_unit = parsed.get("requested_unit")
    if not req_unit:
        return result

    note = (
        "Wholesale mandi prices are always displayed in quintals (₹/quintal) only — "
        "only retail stores provide kg or gms rates (Kg / gms unit not available)."
    )
    result["unit_note"] = note
    base_ans = str(result.get("answer") or "").strip()
    if "wholesale mandi prices are always displayed in quintals" not in base_ans.lower():
        result["answer"] = f"{note} {base_ans}".strip()
    return result

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
            if subj:
                return {
                    "intent": "out_of_scope",
                    "answer": (
                        f'"{subj}" is not an agricultural commodity tracked in this mandi database. '
                        f"Available commodities: {avail} (across {len(state_list)} states). "
                        f'Try: "What is the tomato price in Chennai?" or "Which market has the cheapest onion price?"'
                    ),
                    "columns": [], "rows": [], "count": 0, "source_date": latest, "sql_used": None,
                    "supported_commodities": avail_commodities,
                    "supported_states": state_list,
                }

            # General / multi-commodity queries without a single named vegetable
            has_compare = bool(parsed.get("has_compare"))
            has_trend = bool(parsed.get("has_trend"))

            # Combined state comparison + multi-vegetable trend (e.g. "compare the top two states and provide me a trend graph of all the top 3 vegetables")
            if has_trend:
                top_vegs = [c for c in ("Tomato", "Onion", "Potato") if c in avail_commodities]
                if len(top_vegs) < 3:
                    top_vegs = avail_commodities[:3]
                ph_v = ",".join("?" for _ in top_vegs)
                sql = (
                    f"SELECT arrival_date, commodity, CAST(ROUND(AVG(modal_price)) AS INTEGER) AS avg_modal "
                    f"FROM mandi_prices WHERE commodity IN ({ph_v}) "
                    f"GROUP BY arrival_date, commodity ORDER BY arrival_date ASC, commodity ASC"
                )
                raw_rows = conn.execute(sql, top_vegs).fetchall()
                by_date: dict[str, dict[str, int]] = {}
                for d_val, c_val, p_val in raw_rows:
                    by_date.setdefault(d_val, {})[c_val] = int(p_val)
                cols = ["Date", *[f"{v} (₹/quintal)" for v in top_vegs]]
                out = [
                    [d_key, *[by_date[d_key].get(v, 0) for v in top_vegs]]
                    for d_key in sorted(by_date.keys())
                ]

                state_summary = ""
                if has_compare:
                    st_sql = (
                        f"SELECT state, CAST(ROUND(AVG(modal_price)) AS INTEGER) AS avg_p, COUNT(*) AS cnt "
                        f"FROM mandi_prices WHERE commodity IN ({ph_v}) AND arrival_date=? "
                        + (f"AND state IN ({','.join('?' for _ in states)}) " if len(states) >= 2 else "")
                        + "GROUP BY state ORDER BY cnt DESC, avg_p ASC LIMIT 2"
                    )
                    st_params = [*top_vegs, latest, *(states if len(states) >= 2 else [])]
                    st_rows = conn.execute(st_sql, st_params).fetchall()
                    if len(st_rows) >= 2:
                        state_summary = (
                            f"Top 2 states comparison ({_fmt_date(latest)}): {st_rows[0][0]} averages "
                            f"₹{st_rows[0][1]:,}/quintal vs {st_rows[1][0]} at ₹{st_rows[1][1]:,}/quintal across {', '.join(top_vegs)}. "
                        )
                answer = (
                    f"{state_summary}21-day wholesale price trend across the top {len(top_vegs)} vegetables "
                    f"({', '.join(top_vegs)}) in ₹/quintal from {_fmt_date(out[0][0]) if out else ''} to {_fmt_date(out[-1][0]) if out else ''}."
                )
                return {
                    "intent": "trend",
                    "answer": answer,
                    "columns": cols,
                    "rows": out,
                    "count": len(out),
                    "source_date": latest,
                    "sql_used": sql,
                    "chart_type": "line",
                    "chart": _chart_payload(cols, out),
                    "supported_commodities": avail_commodities,
                    "supported_states": state_list,
                }

            if intent == "compare":
                cols = ["State", "Avg Modal Price (₹/quintal)", "Commodities", "Markets Covered"]
                where_st = f"AND state IN ({','.join('?' for _ in states)}) " if states else ""
                sql = (
                    f"SELECT state, CAST(ROUND(AVG(modal_price)) AS INTEGER), COUNT(DISTINCT commodity), COUNT(DISTINCT market) "
                    f"FROM mandi_prices WHERE arrival_date=? {where_st}"
                    f"GROUP BY state ORDER BY AVG(modal_price) ASC LIMIT 12"
                )
                params = [latest, *states] if states else [latest]
                rows = conn.execute(sql, params).fetchall()
                out = [list(r) for r in rows]
                cheapest_st = out[0] if out else ["—", 0]
                answer = (
                    f"Comparing wholesale mandi prices across {len(out)} states (as of {_fmt_date(latest)}): "
                    f"{cheapest_st[0]} has the lowest overall average modal rate at ₹{cheapest_st[1]:,}/quintal."
                )
                return {
                    "intent": "compare",
                    "answer": answer,
                    "columns": cols,
                    "rows": out,
                    "count": len(out),
                    "source_date": latest,
                    "sql_used": sql,
                    "chart_type": "bar",
                    "chart": _chart_payload(cols, out),
                    "supported_commodities": avail_commodities,
                    "supported_states": state_list,
                }

            if intent == "cheapest":
                cols = ["Commodity", "Market", "District", "State", "Modal Price (₹/quintal)"]
                where_st = "AND state=? " if states else ""
                sql = (
                    f"SELECT commodity, market, district, state, modal_price FROM mandi_prices "
                    f"WHERE arrival_date=? AND modal_price IS NOT NULL {where_st}"
                    f"ORDER BY modal_price ASC LIMIT 10"
                )
                params = [latest, states[0]] if states else [latest]
                rows = conn.execute(sql, params).fetchall()
                out = [list(r) for r in rows]
                scope = f" in {states[0]}" if states else ""
                answer = (
                    f"Lowest wholesale mandi rates{scope} on {_fmt_date(latest)}: "
                    f"{out[0][0]} at {out[0][1]} ({out[0][3]}) is ₹{out[0][4]:,}/quintal."
                    if out else f"No records found{scope}."
                )
                return {
                    "intent": "cheapest",
                    "answer": answer,
                    "columns": cols,
                    "rows": out,
                    "count": len(out),
                    "source_date": latest,
                    "sql_used": sql,
                    "chart_type": "bar",
                    "chart": _chart_payload(cols, out),
                    "supported_commodities": avail_commodities,
                    "supported_states": state_list,
                }

            # Default overview across all tracked commodities (for price / search without a specific vegetable)
            cols = ["Commodity", "Avg Modal Price (₹/quintal)", "Min Price (₹/quintal)", "Max Price (₹/quintal)", "Markets"]
            where_st = "AND state=? " if states else ("AND district=? " if districts else ("AND market=? " if markets else ""))
            place_param = [states[0]] if states else ([districts[0]] if districts else ([markets[0]] if markets else []))
            place_label = (markets or districts or states or [""])[0]
            sql = (
                f"SELECT commodity, CAST(ROUND(AVG(modal_price)) AS INTEGER), MIN(min_price), MAX(max_price), COUNT(DISTINCT market) "
                f"FROM mandi_prices WHERE arrival_date=? {where_st}"
                f"GROUP BY commodity ORDER BY AVG(modal_price) ASC"
            )
            rows = conn.execute(sql, [latest, *place_param]).fetchall()
            out = [list(r) for r in rows]
            scope = f" in {place_label}" if place_label else " across India"
            answer = (
                f"Wholesale mandi price summary{scope} for {_fmt_date(latest)} across {len(out)} tracked commodities "
                f"(all rates in ₹/quintal)."
            )
            return {
                "intent": intent if intent != "unknown" else "search",
                "answer": answer,
                "columns": cols,
                "rows": out,
                "count": len(out),
                "source_date": latest,
                "sql_used": sql,
                "chart_type": "bar",
                "chart": _chart_payload(cols, out),
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
                    "source_date": latest, "sql_used": sql, "chart_type": "bar", "chart": _chart_payload(cols, out)}
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
    chart_data = _chart_payload(columns, rows) if chart_type else []
    if count and len(chart_data) < 2 and parsed and parsed.get("commodity"):
        try:
            fallback_res = run_query(parsed)
            if fallback_res.get("chart") and len(fallback_res["chart"]) >= 2:
                chart_type = fallback_res.get("chart_type") or "bar"
                chart_data = fallback_res["chart"]
        except Exception:
            pass
    out: dict = {
        "intent": "llm_sql" if count else ("out_of_scope" if (parsed or {}).get("unknown_subject") else "llm_sql"),
        "answer": answer,
        "columns": columns if count else [],
        "rows": rows,
        "count": count,
        "source_date": latest,
        "sql_used": result["sql"],
        "chart_type": chart_type,
        "chart": chart_data,
    }
    if not count and avail_commodities:
        out["supported_commodities"] = avail_commodities
        out["supported_states"] = state_list
    return out
