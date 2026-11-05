# DATA GURU — Backend V2

Run:

```
pip install -r requirements.txt
python seed_data.py          # 924 rows, 21 days
python -m uvicorn main:app --port 8000
```

Endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | `{"status": "ok", "version": "v2"}` |
| `GET /api/status` | record count, latest date, whether the LLM and live sync are configured |
| `GET /api/meta` | commodities, states, date range, day count |
| `GET /api/examples` | example questions for the UI |
| `POST /api/ask` | `{"question", "history"}` → answer, rows, chart, engine, SQL used |
| `POST /api/transcribe` | raw audio (`webm`/`wav`/`ogg`/`mp4`) → Groq Whisper transcription |

## Optional configuration (copy `.env.example` → `.env`)

```
DATA_GOV_API_KEY=...        # live AGMARKNET prices via fetch_daily.py
LLM_PROVIDER=groq           # openai | groq | together | openrouter | ollama | gemini
LLM_API_KEY=...
LLM_SUMMARY=true            # AI-written answer sentences
```

Without either key the app runs fully on the rule engine and the seed dataset.

## Data

```
python seed_data.py                     # deterministic 21-day demo dataset
python load_data.py path/to/file.csv    # any AGMARKNET CSV
python fetch_daily.py                   # live sync (needs DATA_GOV_API_KEY)
```

## Tests

```
python test_v2.py     # intents, trend, follow-ups, SQL guard, LLM fallback
python test_sync.py   # data.gov.in sync path (mocked API)
```
