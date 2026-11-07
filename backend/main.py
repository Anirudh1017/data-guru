from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import llm
import settings
from db import get_conn, init_db
from parser import parse
from queries import apply_unit_conversion, run_generated_sql, run_query
from sql_guard import UnsafeSQLError

app = FastAPI(title="DATA GURU", version="v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


class Turn(BaseModel):
    question: str = ""
    parsed: dict | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    history: list[Turn] = Field(default_factory=list)


@app.get("/api/health")
@app.get("/health")
def health():
     return {"status": "ok", "version": "v2"}
 
@app.get("/v1/models")
def models():
    return {"data": [{"id": settings.LLM_MODEL or "gpt-oss-120b", "object": "model"}]}
@app.get("/api/status")
def status():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM mandi_prices").fetchone()[0]
        latest = conn.execute("SELECT MAX(arrival_date) FROM mandi_prices").fetchone()[0]
    return {"records": total, "latest_date": latest, **settings.public_config()}


@app.get("/api/examples")
def examples():
    return {"examples": [
        "What is the tomato price in Chennai?",
        "Which market has the cheapest onion price?",
        "Compare potato prices in Tamil Nadu and Kerala.",
        "How have onion prices moved over the last two weeks?",
    ]}


@app.get("/api/meta")
def meta():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM mandi_prices").fetchone()[0]
        latest = conn.execute("SELECT MAX(arrival_date) FROM mandi_prices").fetchone()[0]
        commodities = [r[0] for r in conn.execute("SELECT DISTINCT commodity FROM mandi_prices ORDER BY commodity")]
        states = [r[0] for r in conn.execute("SELECT DISTINCT state FROM mandi_prices ORDER BY state")]
        dates = [r[0] for r in conn.execute("SELECT DISTINCT arrival_date FROM mandi_prices ORDER BY arrival_date")]
    return {
        "total_records": total,
        "latest_date": latest,
        "date_range": [dates[0], dates[-1]] if dates else None,
        "days": len(dates),
        "commodities": commodities,
        "states": states,
    }


def _llm_answer(req: AskRequest, history: list[dict], parsed: dict) -> dict | None:
    """Try the LLM path. Returns None so the caller can fall back to rules."""
    if not llm.available() or parsed.get("is_junk"):
        return None
    # For multi-commodity trend/compare queries without a specific named commodity,
    # or when retail kg/gms units are requested, use the deterministic rule engine
    # so multi-series pivoted charts and wholesale quintal-only pricing are guaranteed.
    if parsed.get("requested_unit") is not None:
        return None
    if not parsed.get("commodity") and not parsed.get("unknown_subject") and (parsed.get("has_trend") or parsed.get("has_compare")):
        return None
    try:
        generated = llm.generate_sql(req.question, history)
        sql = generated["sql"]
        # If an unknown out-of-scope subject was parsed and the LLM didn't filter with a WHERE clause,
        # reject unfiltered table dumps so out-of-scope queries don't return random rows.
        if (
            parsed.get("unknown_subject")
            and not parsed.get("commodity")
            and not parsed.get("states")
            and not parsed.get("districts")
            and not parsed.get("markets")
            and "where" not in sql.lower()
        ):
            return None
        result = run_generated_sql(sql, parsed=parsed)
    except (UnsafeSQLError, ValueError, KeyError):
        return None
    except Exception:
        return None

    result["engine"] = "llm"
    result["rationale"] = generated.get("rationale", "")
    result["parsed"] = parsed
    if result["count"] and result["columns"]:
        result["answer"] = llm.phrase_answer(
            req.question, result["columns"], result["rows"], result["answer"]
        )
    return result


@app.post("/api/ask")
def ask(req: AskRequest):
    history = [t.model_dump() for t in req.history]
    parsed = parse(req.question, history)

    result = _llm_answer(req, history, parsed)

    if result is None:
        result = run_query(parsed)
        result["parsed"] = parsed
        result["engine"] = "rules"
    result = apply_unit_conversion(result, parsed)
    result["question"] = req.question
    return result


@app.post("/api/transcribe")
async def transcribe(request: Request):
    if not settings.stt_available():
        raise HTTPException(status_code=503, detail="Groq STT is not configured")
    audio_bytes = await request.body()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio body")
    content_type = (request.headers.get("content-type") or "audio/webm").split(";")[0].strip()
    filename = request.headers.get("x-audio-filename") or (
        "speech.wav" if "wav" in content_type else "speech.ogg" if "ogg" in content_type else "speech.mp4" if "mp4" in content_type else "speech.webm"
    )
    try:
        text = llm.transcribe_audio(audio_bytes, filename=filename, content_type=content_type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}") from exc
    return {"text": text, "model": settings.STT_MODEL}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
