# Changelog

All notable changes to **DATA GURU — Indian Mandi Price Portal** are documented in this file.

## [2.2.0] — 2026-11-05

### Added
- **Multi-Series Analytics & Aggregate Query Support**:
  - Broadened natural-language query parsing to support category-wide and multi-commodity queries without requiring a single commodity name.
  - Added multi-series line and bar chart rendering (`ChartView.tsx`) with interactive legends for comparing multiple commodities over time.
- **Persistent Commodity & State Navigation**:
  - Added a persistent quick-filter directory on result views so users can switch between tracked commodities and covered states at any point in a conversation.
- **Wholesale Unit Policy Enforcement**:
  - Standardized all price reporting strictly to wholesale quintal rates (`₹/quintal`) and added clear guidance when retail units (`kg` or `gms`) are queried.

## [2.1.0] — 2026-11-05

### Added
- **Interactive Visualizations Across Intents**:
  - Added chart generation for all query types along with an interactive **Bar / Line** chart switcher in result cards.

### Changed
- **Portal Identity & Single-Frame Layout**:
  - Updated the portal title to **Indian Mandi Price Portal** with a streamlined header and single-line subtitle.
  - Redesigned the home view into an evenly spaced, full-width single-frame layout (`1280px` container) with simplified quick-start presets and dataset coverage metrics.
  - Updated clone and setup documentation in `README.md`.

## [2.0.0] — 2026-11-04

### Added
- Conversational mandi price portal with FastAPI + SQLite backend and React + Vite + Recharts frontend.
- Read-only guarded LLM-to-SQL engine (`backend/llm.py`, `backend/sql_guard.py`) with deterministic rule-based fallback (`backend/parser.py`, `backend/queries.py`).
- Voice search via Groq Whisper (`whisper-large-v3-turbo`) with VAD and browser Web Speech API (`en-IN`) fallback.
- Live AGMARKNET daily price sync (`backend/fetch_daily.py`) and 21-day deterministic seed dataset (`924` records across `6` commodities and `12` states).
