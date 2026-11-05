# V2 — shipped

Everything below is built, tested, and running. This document is now a reference for what was
done and what remains.

## Shipped

### 1. Live data sync — `backend/fetch_daily.py`
- Reads `DATA_GOV_API_KEY` from `backend/.env` (free at data.gov.in).
- Pages through `9ef84268-d588-465a-a308-a864a43d0070` (Current Daily Price of Various
  Commodities from Various Markets), 1000 records per page, with a 0.4s pause between pages.
- `ingest.py` maps every known column spelling to the canonical schema, normalises names
  (`K.R. Market` survives, `TAMIL NADU` → `Tamil Nadu`), parses both ISO and `DD/MM/YYYY` dates,
  and strips commas/rupee symbols from prices.
- Upserts are **date-scoped**: only the fetched dates are replaced, so daily syncs grow history
  and re-running changes nothing.
- Verified without a key: `python test_sync.py` mocks the API and checks pagination,
  normalisation and idempotent re-sync.

### 2. LLM → SQL — `backend/llm.py`, `backend/sql_guard.py`
- Schema description + few-shot examples (cheapest, compare, trend) in the system prompt.
- Works with any OpenAI-compatible endpoint. `LLM_PROVIDER` selects the provider and defaults;
  `LLM_BASE_URL` / `LLM_MODEL` override anything. `ollama` needs no key.
- Every generation passes through the guard: single statement, no comments, `SELECT`/`WITH` only,
  forbidden keywords rejected, only `mandi_prices` may be referenced, `LIMIT` clamped to 200.
- Execution happens on a **read-only connection** with a progress-handler step budget and a
  5-second time budget.
- Any unsafe SQL, provider error or timeout falls back to the rule engine. The response includes
  `"engine": "llm" | "rules"`, the model's rationale, and the exact SQL.
- Rule-parsed context is still attached to LLM answers, so follow-ups keep working.

### 3. AI-written answers
- `llm.phrase_answer()` turns the returned rows into one or two sentences in Indian digit
  grouping, constrained to only the rows given. `LLM_SUMMARY=false` disables it.
- Falls back to the template sentence on any failure.

### 4. Voice search — `frontend/src/hooks/useSpeech.ts`
- Web Speech API, `en-IN`, live interim transcript, mic button pulses while listening.
- Clear errors for blocked permissions, no microphone, and unsupported browsers.
- No server, no key. Requires Chrome or Edge.

### 5. Conversation context
- The browser keeps the last 6 turns and sends them with each request.
- Follow-ups inherit commodity, then intent, then state: "And in Kerala?" re-runs the previous
  comparison scoped to Kerala.
- Previous turns collapse into a one-line summary; the latest turn stays open.
- "Ask next" chips are generated from the current intent and commodity.

### 6. Trends — `trend` intent
- "How have onion prices moved over the last two weeks?" returns daily average modal prices.
- Line chart with a zoomed y-axis (the data barely moves, so a zero baseline flattens it);
  the daily table is behind "Show all N daily values".

### 7. Dataset
- `seed_data.py` now builds 924 rows: 44 markets × 21 days, 6 commodities, 12 states, two
  vines of volatility. Deterministic, so tests and screenshots never drift.

## Verification

```
cd backend && python test_v2.py          # 38 checks
cd backend && python test_sync.py        # 11 checks
cd frontend && node scripts/verify.mjs   # 26 browser checks
```

## Not done, and why

| Idea | Why it's not here yet |
|---|---|
| Multi-dataset search (add a dataset picker) | dataset wiring is in place (`ingest.py`); it needs a product decision about which datasets to offer first |
| Persisted conversations | in-memory per tab today; needs a table + session id — small, and only useful once more than one user runs it |
| Server-side speech-to-text | on-device browser speech is simpler and key-free; a backend STT only makes sense for non-Chrome users |
| Deployment | code is ready (purpose-built API + static dist); it needs a host choice (Railway/Fly/Render/VPS) and a decision about where SQLite lives |
