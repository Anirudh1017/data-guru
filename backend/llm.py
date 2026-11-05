"""LLM layer: natural language -> safe SQL -> natural language answer.

Works with any OpenAI-compatible endpoint (OpenAI, Groq, Together, OpenRouter, Ollama,
Gemini's compat endpoint). Every function degrades to the rule-based V1 path when no
provider is configured or the call fails.
"""
import json
import re
from typing import Iterable

import httpx

import settings

SCHEMA = """
Table: mandi_prices (one row = one commodity at one market on one day)
  id           INTEGER primary key
  state        TEXT   e.g. 'Tamil Nadu', 'Kerala', 'Maharashtra'
  district     TEXT   e.g. 'Chennai', 'Madurai'
  market       TEXT   e.g. 'Koyambedu', 'Azadpur'
  commodity    TEXT   e.g. 'Tomato', 'Onion', 'Potato'
  variety      TEXT   e.g. 'Desi', 'Hybrid', 'Chipsona'
  arrival_date TEXT   ISO 'YYYY-MM-DD'
  min_price    INTEGER rupees per quintal
  max_price    INTEGER rupees per quintal
  modal_price  INTEGER rupees per quintal  <-- the representative price
""".strip()

RULES = """
Rules:
- Output ONE SQLite SELECT statement over mandi_prices only. Never write data.
- Use modal_price for "price" unless min/max is asked for.
- Commodity, state, district and market values are Title Case (tracked commodities: Tomato, Onion, Potato, Wheat, Rice, Banana). Compare with = or LIKE, case-insensitively using LOWER() when unsure.
- When the question asks for a current/latest price, a bare commodity name (e.g. "Tomato"), or cheapest/lowest/top N markets (and NOT a trend over time), filter to the latest date with `AND arrival_date = (SELECT MAX(arrival_date) FROM mandi_prices)`.
- For "cheapest/lowest/top N" or a bare commodity name, use `SELECT market, district, state, modal_price` with `ORDER BY modal_price ASC LIMIT N` (default 5).
- If the user asks about a non-agricultural item or an item not in mandi_prices (e.g. "Cloth", "Gold"), still filter by `WHERE LOWER(commodity) = '<item>'` so the query cleanly returns 0 rows. Never return unfiltered rows when the user's subject is unrecognizable.
- For comparisons across states use `GROUP BY state` with `CAST(ROUND(AVG(modal_price)) AS INTEGER) AS avg_modal`.
- For trends or movements over time (including "last two weeks", "over time", "how have prices moved"), NEVER filter `arrival_date` in the WHERE clause; always query all dates in the table with `GROUP BY arrival_date ORDER BY arrival_date ASC LIMIT 60`.
- Always include a LIMIT of 200 or less.
""".strip()
FEW_SHOT = [
    (
        "Which market has the cheapest tomato price in Tamil Nadu?",
        "SELECT market, district, state, modal_price FROM mandi_prices "
        "WHERE LOWER(commodity)='tomato' AND LOWER(state)='tamil nadu' "
        "AND arrival_date=(SELECT MAX(arrival_date) FROM mandi_prices) "
        "ORDER BY modal_price ASC LIMIT 5",
    ),
    (
        "Compare potato prices in Tamil Nadu and Kerala",
        "SELECT state, CAST(ROUND(AVG(modal_price)) AS INTEGER) AS avg_modal, "
        "COUNT(DISTINCT market) AS markets FROM mandi_prices "
        "WHERE LOWER(commodity)='potato' AND LOWER(state) IN ('tamil nadu','kerala') "
        "GROUP BY state ORDER BY avg_modal ASC LIMIT 50",
    ),
    (
        "How have onion prices moved over the last two weeks?",
        "SELECT arrival_date, CAST(ROUND(AVG(modal_price)) AS INTEGER) AS avg_modal "
        "FROM mandi_prices WHERE LOWER(commodity)='onion' "
        "GROUP BY arrival_date ORDER BY arrival_date ASC LIMIT 60",
    ),
]


def available() -> bool:
    return settings.llm_available()


def _chat(messages: list[dict], temperature: float = 0.0, max_tokens: int = 500) -> str:
    headers = {"Content-Type": "application/json"}
    if settings.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"

    payload = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
    with httpx.Client(timeout=settings.LLM_TIMEOUT) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict:
    """Models sometimes wrap JSON in prose or fences."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _history_block(history: Iterable[dict] | None) -> str:
    turns = list(history or [])[-4:]
    if not turns:
        return ""
    lines = ["Recent conversation (resolve follow-ups like 'and in Kerala?' from this):"]
    for turn in turns:
        q = str(turn.get("question", "")).strip()
        if q:
            lines.append(f"- user asked: {q}")
    return "\n".join(lines) + "\n\n"


def generate_sql(question: str, history: list[dict] | None = None) -> dict:
    """Ask the model for one SELECT. Raises on transport/parse failure."""
    examples = "\n".join(f"Q: {q}\nSQL: {s}" for q, s in FEW_SHOT)
    messages = [
        {
            "role": "system",
            "content": (
                "You translate questions about Indian agricultural mandi prices into SQLite.\n"
                f"{SCHEMA}\n\n{RULES}\n\nExamples:\n{examples}\n\n"
                'Reply with JSON only: {"sql": "<one SELECT statement>", "rationale": "<short reason>"}'
            ),
        },
        {
            "role": "user",
            "content": f"{_history_block(history)}Question: {question}",
        },
    ]
    raw = _chat(messages, temperature=0.0, max_tokens=1024)
    data = _extract_json(raw)
    sql = str(data.get("sql", "")).strip()
    if not sql:
        raise ValueError("Model returned no SQL")
    return {"sql": sql, "rationale": str(data.get("rationale", "")).strip()}


def phrase_answer(
    question: str,
    columns: list[str],
    rows: list[list],
    fallback: str,
) -> str:
    """Turn result rows into one plain-English sentence. Falls back on any failure."""
    if not settings.LLM_SUMMARY or not rows:
        return fallback

    preview = [columns] + (rows[:10] if len(rows) <= 10 else rows[:5] + rows[-5:])
    messages = [
        {
            "role": "system",
            "content": (
                "You are DATA GURU. Answer in 1-2 short sentences using ONLY the rows given. "
                "Prices are rupees per quintal. For date series, explicitly state whether prices "
                "moved up, moved down, or stayed flat from the first date to the last date. "
                "Round sensibly and use Indian digit grouping (e.g. 1,800). "
                "Do not invent rows, markets or numbers. No markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\n"
                f"Result rows (first row is the header):\n{json.dumps(preview, ensure_ascii=False)}"
            ),
        },
    ]
    try:
        text = _chat(messages, temperature=0.2, max_tokens=600).strip()
        return text or fallback
    except Exception:
        return fallback


STT_PROMPT = (
    "Indian agricultural mandi prices: Tomato, Onion, Potato, Wheat, Rice, Banana, "
    "Tamil Nadu, Kerala, Karnataka, Maharashtra, Punjab, Delhi, Chennai, Koyambedu, "
    "Kochi, Madurai, Coimbatore, Salem, cheapest, compare, modal price."
)


def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "speech.webm",
    content_type: str = "audio/webm",
) -> str:
    """Transcribe spoken audio via Groq / OpenAI Whisper-compatible /audio/transcriptions."""
    if not settings.stt_available():
        raise RuntimeError("Speech-to-text API key is not configured")
    if not audio_bytes:
        raise ValueError("Empty audio payload")

    url = f"{settings.STT_BASE_URL.rstrip('/')}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.STT_API_KEY}"}
    data = {
        "model": settings.STT_MODEL,
        "language": "en",
        "response_format": "json",
        "prompt": STT_PROMPT,
    }
    files = {"file": (filename or "speech.webm", audio_bytes, content_type or "audio/webm")}
    with httpx.Client(timeout=settings.LLM_TIMEOUT) as client:
        resp = client.post(url, headers=headers, data=data, files=files)
        resp.raise_for_status()
        payload = resp.json()
    return str(payload.get("text", "")).strip()
