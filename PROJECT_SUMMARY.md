# DATA GURU — Indian Mandi Price Portal
## Comprehensive Project Summary & Architecture Document

---

## 1. Executive Overview

**DATA GURU — Indian Mandi Price Portal** is a production-grade conversational intelligence platform designed to democratize access to Indian agricultural market pricing data (AGMARKNET). Users can query wholesale rates in natural English or via voice transcription, receiving immediate answers, interactive data visualizations (Bar and Line charts), structured data tables, and conversational follow-up suggestions.

The platform is designed around three architectural pillars:
1. **Zero-Configuration Accessibility:** Operates completely without API keys using a deterministic rule-based natural language parser and query builder.
2. **AI-Powered Acceleration:** When configured with an LLM provider (Groq, OpenAI, Together, OpenRouter, Ollama, or Gemini), natural language queries are automatically translated into SQL and summarized with Indian numeric formatting.
3. **Defense-in-Depth Security:** Every model-generated query is strictly guarded by an AST/token validator and executed on a read-only SQLite connection, completely neutralizing prompt injections, data tampering, and exfiltration.

---

## 2. Technology Stack

### 2.1. Frontend
- **Framework & Language:** React 19, TypeScript
- **Build Tool:** Vite 8.3 (with Rolldown engine)
- **Data Visualization:** Recharts (responsive single-series & multi-series Line and Bar charts)
- **Styling:** Custom CSS built on design tokens, responsive typography (`Fraunces` serif + `Inter` sans-serif), CSS grid/flexbox layouts. Zero UI framework bloat.
- **Voice / Speech-to-Text:** Web Speech API (`en-IN`) with fallback + Groq Whisper (`whisper-large-v3-turbo`) integration via MediaRecorder and Web Audio API with Voice Activity Detection (VAD).

### 2.2. Backend
- **Framework:** FastAPI (Python 3.10+)
- **Server:** Uvicorn ASGI server with full CORS support
- **Database:** SQLite 3 with WAL mode, read-only connection sandboxing (`mode=ro`), step/instruction limits, and timeout boundaries.
- **HTTP Client:** HTTPX (async & sync connection pools for LLM and STT integrations).
- **Audio Processing:** Native multipart and raw audio payload ingestion (`audio/webm`, `audio/wav`, `audio/ogg`, `audio/mp4`).

### 2.3. AI & Speech Models
- **Primary LLM:** Groq Cloud running `openai/gpt-oss-120b` (or any OpenAI-compatible provider: OpenAI `gpt-4o-mini`, Together AI `meta-llama/Llama-3.3-70B-Instruct-Turbo`, Ollama local `llama3.1`).
- **Primary Speech-to-Text:** Groq Whisper (`whisper-large-v3-turbo`) primed with Indian mandi vocabulary (`Koyambedu`, `Mattuthavani`, `Tamil Nadu`, `Kerala`, etc.).
- **Fallback Speech-to-Text:** Browser-native Web Speech API (`en-IN`).

---

## 3. Dataset & Domain Architecture

### 3.1. Data Source
- **Primary Live Sync:** [data.gov.in](https://data.gov.in) — Resource ID: `9ef84268-d588-465a-a308-a864a43d0070` (Current Daily Price of Various Commodities from Various Markets).
- **Ingestion Pipeline:** `fetch_daily.py` & `ingest.py` perform idempotent, date-scoped upserts.
- **Deterministic Seed Data:** `seed_data.py` generates 924 realistic mandi records covering 21 continuous days across 44 mandis.

### 3.2. Scope of Coverage
- **6 Tracked Commodities:** Banana, Onion, Potato, Rice, Tomato, Wheat.
- **12 Indian States:** Andhra Pradesh, Delhi, Gujarat, Karnataka, Kerala, Madhya Pradesh, Maharashtra, Punjab, Rajasthan, Tamil Nadu, Uttar Pradesh, West Bengal.
- **Time Window:** 21 days of historical data for trend analysis and movement tracking.

### 3.3. Mandatory Domain Rule: Wholesale Quintal-Only Policy
- All official AGMARKNET mandi records are reported and traded strictly in **Rupees per quintal (₹/quintal)**, where:
  $$1\text{ quintal} = 100\text{ kg} = 100,000\text{ grams}$$
- Retail units (`kg`, `gms`) do not exist in wholesale mandis; retail rates apply only to local consumer shops.
- When users request `kg` or `gms`, the portal provides explicit policy guidance and displays the rates in official `₹/quintal` values.

---

## 4. Key Functional Capabilities & Modules

### 4.1. Conversational Query Routing & Dual Engine
```
User Natural Language Question + Context History
                  │
                  ▼
        Is LLM configured & query valid?
             /                  \
           YES                   NO (or LLM failure / unsafe SQL)
           /                      \
   LLM writes SELECT          Rule-based Parser (parser.py)
          │                                │
   sql_guard.py validates            Query Builder (queries.py)
          │                                │
   Execute Read-Only SQLite         Execute Parameterized SQLite
          │                                │
   Phrase Answer (LLM)               Deterministic Answer
             \                            /
              ▼                          ▼
          JSON Payload: {answer, columns, rows, chart, chart_type, engine}
```

### 4.2. Multi-Turn Context Tracking
- The client maintains the last 6 conversational turns (`history`).
- Follow-up queries inherit context without repeating words:
  - *Turn 1:* "Which market has the cheapest tomato price?"
  - *Turn 2:* "And in Kerala?" $\rightarrow$ Automatically inherits `commodity=Tomato` and `intent=cheapest`, scoping the query strictly to `state=Kerala`.
- Previous turns collapse cleanly into accordion summaries, keeping the latest turn focal.

### 4.3. Multi-Series Trend & Aggregate Analytics
- Handles complex aggregate queries without requiring a specific vegetable name (e.g. *"compare the top two states and provide me a trend graph of all the top 3 vegetables"*).
- The visualization engine pivots time-series data into multi-column series, rendering multi-line charts with interactive legends and Bar/Line toggles.

### 4.4. Security Guard (`sql_guard.py`)
- Restricts SQL statements to a single `SELECT` or `WITH ... SELECT`.
- Enforces an upper `LIMIT` clamp ($\le 200$).
- Rejects writes, DDL, comments (`--`, `/*`), `PRAGMA`, multiple statements, and table access outside `mandi_prices`.
- Executes via an isolated SQLite connection with a progress handler step budget and a 5-second deadline.

---

## 5. UI/UX Design System (Impeccable & Taste Craft)

- **Single-Frame Viewport:** Fits the entire home landing experience into a single viewport frame (`1440×900` with 0px overflow).
- **Proportional Spacing Rhythm:** Symmetrical 24px vertical cadence between Hero title, compact search bar, preset chips, and bottom directory.
- **Two-Card Bento Parameter Directory:**
  - *Left Card:* **Tracked Vegetables & Crops** in a `2×3` responsive grid.
  - *Right Card:* **Covered States** in an elongated `2×6` horizontal grid.
  - Slim, low-profile pill buttons (`padding: 6px 12px; border-radius: 999px`) that align both cards at an identical height.
- **Persistent Directory on Results View:** Commodities and states remain pinned directly beneath the search bar on result pages so users can switch entities with a single click.
- **Accessible State Handling:** Complete coverage for voice recording pulse states, loading skeletons, error recovery banners, and keyboard accessibility.

---

## 6. Comprehensive Test Case Matrix

### 6.1. Positive Test Cases (Functional Verification)

| # | Test Category | Sample Query | Expected System Behavior |
|---|---|---|---|
| **P1** | **Direct City Price Lookup** | `What is the tomato price in Chennai?` | Returns modal price in Chennai mandis (Koyambedu, Parry's Corner), displays comparison chart and structured table. |
| **P2** | **Specific Market Lookup** | `What is the onion price at Koyambedu?` | Identifies `market=Koyambedu`, filters modal rate, returns single-market min/modal/max chart breakdown. |
| **P3** | **Cheapest Market Discovery** | `Which market has the cheapest onion price?` | Ranks top 5 mandis across India in ascending price order, displays bar chart visualization. |
| **P4** | **State-Scoped Cheapest** | `Which market has the lowest tomato price in Tamil Nadu?` | Scopes search to `state=Tamil Nadu`, lists top 5 lowest mandis in Tamil Nadu. |
| **P5** | **State Comparison** | `Compare potato prices in Tamil Nadu and Kerala.` | Groups by state, calculates average modal price, outputs comparison bar chart. |
| **P6** | **21-Day Historical Trend** | `How have onion prices moved over the last two weeks?` | Queries 21 days of data, calculates direction (up/down/flat), renders line chart with date x-axis. |
| **P7** | **Multi-Series Trend Graph** | `compare the top two states and provide me a trend graph of all the top 3 vegetables` | Generates 3-line trend chart for Onion, Potato, Tomato over 21 days with legend + state summary without throwing unknown commodity error. |
| **P8** | **Category-Wide Rate Query** | `Show me vegetable prices in Chennai` | Summarizes rates across all tracked commodities in Chennai without failing on missing single crop name. |
| **P9** | **Bare Commodity Name** | `Tomato` | Treats bare crop name as a browse request, shows top markets and modal price distribution. |
| **P10** | **Conversational Follow-up** | *Turn 1:* `Which market has the cheapest tomato price?`<br>*Turn 2:* `And in Kerala?` | Inherits `Tomato` and `cheapest` intent, filters results strictly to Kerala mandis; collapses Turn 1 into compact summary. |
| **P11** | **Interactive Visualization Switcher** | *Any valid query with chart* | User clicks **Bar** or **Line** toggle buttons on result card header; chart immediately switches type smoothly. |
| **P12** | **Persistent Filter Navigation** | *Clicking any pill on result view* | Clicking `Onion` or `Karnataka` executes instant filtered query while keeping parameter directory visible. |

---

### 6.2. Policy & Unit Enforcement Cases

| # | Test Category | Sample Query | Expected System Behavior |
|---|---|---|---|
| **U1** | **Kilogram Unit Query** | `What is the tomato price in kg in Chennai?` | Triggers **Wholesale Unit Policy** banner; informs user wholesale prices are displayed in ₹/quintal only (retail stores provide kg); presents official ₹/quintal data. |
| **U2** | **Gram Unit Query** | `Onion price for 500 gms in Tamil Nadu` | Enforces wholesale quintal policy; prevents retail conversion column; outputs official quintal figures. |
| **U3** | **Explicit Multi-Kg Request** | `How much is 2 kg potato in Kerala?` | Rejects retail price generation; explains wholesale trade standards in quintals. |

---

### 6.3. Negative & Security Test Cases

| # | Test Category | Sample Query | Expected System Behavior |
|---|---|---|---|
| **N1** | **Out-of-Scope Commodity** | `Cloth` | Returns 0 records; outputs message stating Cloth is not an agricultural crop in AGMARKNET; renders 6 recovery pills. |
| **N2** | **Non-Agricultural Good** | `What is the price of gold in Mumbai?` | Returns 0 records; does not hallucinate; offers one-click recovery pills for tracked crops. |
| **N3** | **Untracked Crop** | `Avocado price in Chennai` | Identifies Avocado as untracked; provides list of 6 available crops across 12 states. |
| **N4** | **Punctuation & Symbols** | `@#$%^&*!` | Detected by junk filter; rejected before LLM call; returns invalid query guidance. |
| **N5** | **Numeric Mash** | `123456789` | Detected as non-alpha junk; rejected with format guidance. |
| **N6** | **Consonant Keyboard Mash** | `asdfghjkl123` | Classified as junk; returns 0 records and helpful search suggestions. |
| **N7** | **SQL Injection / DDL Attack** | `DROP TABLE mandi_prices;` | Caught by `sql_guard.py`; rejected with `UnsafeSQLError`; safely falls back to read-only rule parser. |
| **N8** | **SQL Write Attack** | `UPDATE mandi_prices SET modal_price=1;` | Blocked by SQL guard tokenizer; write is never executed. |
| **N9** | **Data Exfiltration Attempt** | `SELECT * FROM sqlite_master;` | Blocked because table access is strictly restricted to `mandi_prices`. |
| **N10** | **Stacked Query Attack** | `SELECT * FROM mandi_prices; DELETE FROM mandi_prices;` | Blocked because multiple statements are disallowed. |
| **N11** | **Provider Outage / Network Down** | *Any question with invalid LLM key* | Catches HTTP/network exception gracefully; transparently answers via rule engine with `"engine": "rules"`. |

---

## 7. Operational & Verification Commands

### 7.1. Running the System
```powershell
# 1. Backend Service
cd backend
pip install -r requirements.txt
python seed_data.py
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 2. Frontend Service
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

### 7.2. Automated Test Execution
```powershell
# Backend suite: 39 checks covering rule parsing, trends, SQL guard, LLM fallback, STT
cd backend
python test_v2.py

# Live sync verification (mocked data.gov.in AGMARKNET API)
cd backend
python test_sync.py

# Headless browser suite: 31 checks across 4 viewport sizes (1440, 1024, 768, 390)
cd frontend
node scripts/verify.mjs
```

---

## 8. Summary of Version Milestones

- **v2.0.0:** Initial conversational portal with FastAPI, React, SQLite, Groq Whisper voice search, and data.gov.in daily sync.
- **v2.1.0:** Redesigned single-frame layout, interactive Bar/Line visualization toggles, and unified portal branding.
- **v2.2.0:** Multi-series trend & comparison analytics, persistent commodity/state directory on result views, and wholesale quintal policy enforcement.
- **v2.3.0:** Two-card bento directory (`Tracked Vegetables & Crops` `2×3` + `Covered States` `2×6`), compact centered search bar, and balanced vertical rhythm.
