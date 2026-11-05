# Changelog

All notable changes to **DATA GURU — Indian Mandi Price Portal** are documented in this file.

## [2.1.0] — 2026-11-05

### Added
- **Kg / gms Unit Handling & Automatic Conversion (`backend/parser.py`, `backend/queries.py`, `backend/main.py`, `frontend/src/App.tsx`)**:
  - Detects `kg`, `kgs`, `kilogram`, `gm`, `gms`, and `grams` requests (including explicit quantities such as `500 gms` or `2 kg`).
  - Explicitly informs the user that raw AGMARKNET mandi records do not provide `Kg / gms` units (`1 quintal = 100 kg = 100,000 gms`) and automatically appends a converted `Converted (₹/kg)` or `Converted (₹/gms)` column plus a dedicated unit-conversion banner.
- **Interactive Visualizations for All Query Intents (`backend/queries.py`, `frontend/src/App.tsx`, `frontend/src/App.css`)**:
  - Generates chart payloads across all query intents (`price`, `cheapest`, `compare`, `trend`, `search`, and single-market `Min / Modal / Max` breakdowns).
  - Added an interactive **Bar / Line** chart switcher in the result card header so users can toggle visualizations on demand.

### Changed
- **Portal Title, Header & Subtitle Copy (`frontend/index.html`, `frontend/src/App.tsx`, `frontend/src/App.css`)**:
  - Updated the portal title and hero heading to **`Indian Mandi Price Portal`** (removed `"Indian Agricultural"`).
  - Removed the duplicate `"Indian Mandi Price Portal"` subtitle from the top header bar so only `DATA GURU` is shown on the left and the engine status badge on the right.
  - Updated the single-line hero lead copy to: `"Search daily wholesale vegetable rates (₹/quintal), compare states, and track 21-day price trends across India."` (removed `"find the cheapest mandis"` and updated `"commodity"` to `"vegetable"`).
- **Full-Width Single-Frame Home Layout & Distilled Presets (`frontend/src/App.tsx`, `frontend/src/App.css`)**:
  - Expanded container layout (`max-width: 1280px`) with equal left and right edges.
  - Simplified home page presets to 3 essential one-row query cards and the 4-stat dataset coverage bar (`924 records loaded`, `6 commodities`, `12 states`, `21 days of history`).
  - Balanced vertical spacing evenly across the single viewport frame (`1440×900` with zero scroll overflow).
- **Clone Instructions (`README.md`)**:
  - Added `cd d:\    # any user directory` prior to `git clone` and `cd data-guru`.

## [2.0.0] — 2026-11-04

### Added
- Conversational mandi price portal with FastAPI + SQLite backend and React + Vite + Recharts frontend.
- Read-only guarded LLM-to-SQL engine (`backend/llm.py`, `backend/sql_guard.py`) with deterministic rule-based fallback (`backend/parser.py`, `backend/queries.py`).
- Voice search via Groq Whisper (`whisper-large-v3-turbo`) with VAD and browser Web Speech API (`en-IN`) fallback.
- Live AGMARKNET daily price sync (`backend/fetch_daily.py`) and 21-day deterministic seed dataset (`924` records across `6` commodities and `12` states).
