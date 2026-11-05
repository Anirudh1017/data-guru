"""V2 test suite: intents, trends, follow-ups, SQL guard, LLM fallback."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient
import llm
import main
import settings
from sql_guard import UnsafeSQLError, execute_readonly, validate_sql

client = TestClient(main.app)
failures: list[str] = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  -> {detail}" if not condition else ""))
    if not condition:
        failures.append(name)


def ask(question, history=None):
    r = client.post("/api/ask", json={"question": question, "history": history or []})
    assert r.status_code == 200, r.text
    return r.json()


real_available = llm.available
llm.available = lambda: False
try:
    print("\n== rule-based intents ==")
    d = ask("What is the tomato price in Chennai?")
    check("price intent", d["intent"] == "price" and d["count"] > 0, d["intent"])
    check("price uses latest date", d["source_date"] == "2026-11-04", d["source_date"])

    d = ask("Which market has the cheapest onion price?")
    check("cheapest returns 5", d["intent"] == "cheapest" and d["count"] == 5, d["count"])
    check("cheapest sorted asc", [r[3] for r in d["rows"]] == sorted(r[3] for r in d["rows"]))
    check("cheapest has chart", len(d.get("chart", [])) == 5)

    d = ask("Compare the prices of potatoes in Tamil Nadu and Kerala.")
    check("compare intent", d["intent"] == "compare" and d["count"] == 2, d["count"])
    check("compare chart", len(d.get("chart", [])) == 2)

    d = ask("Which market has the lowest tomato price in Tamil Nadu?")
    check("state-scoped cheapest", d["intent"] == "cheapest" and all(r[2] == "Tamil Nadu" for r in d["rows"]))

    print("\n== trend ==")
    d = ask("How have onion prices moved over the last two weeks?")
    check("trend intent", d["intent"] == "trend", d["intent"])
    check("trend has 21 days", d["count"] == 21, d["count"])
    check("trend chart type", d.get("chart_type") == "line", d.get("chart_type"))
    check("trend chart points", len(d.get("chart", [])) == 21)
    check("trend answer mentions dates", "15 Oct 2026" in d["answer"] and "4 Nov 2026" in d["answer"], d["answer"])

    print("\n== follow-ups ==")
    first = ask("Which market has the cheapest tomato price?")
    history = [{"question": first["question"], "parsed": first["parsed"]}]
    d = ask("And in Kerala?", history)
    check("follow-up inherits commodity", d["parsed"]["commodity"] == "Tomato", d["parsed"])
    check("follow-up scopes state", d["parsed"]["states"] == ["Kerala"], d["parsed"]["states"])
    check("follow-up returns Kerala rows", all(r[2] == "Kerala" for r in d["rows"]), d["rows"][:2])

    print("\n== valid bare commodity, invalid commodity, and junk inputs (rules) ==")
    d_tom = ask("Tomato")
    check("valid bare 'Tomato' returns rows + chart", d_tom["count"] > 0 and len(d_tom.get("chart", [])) > 0, d_tom["count"])

    d_cloth = ask("Cloth")
    check("invalid 'Cloth' returns 0 rows + out_of_scope", d_cloth["count"] == 0 and d_cloth["intent"] == "out_of_scope", d_cloth["intent"])
    check("invalid 'Cloth' lists supported commodities", "Tomato" in (d_cloth.get("supported_commodities") or []) and "Cloth" in d_cloth["answer"], d_cloth["answer"])

    d_junk = ask("@#$%^&*!")
    check("junk '@#$%^&*!' returns 0 rows + invalid", d_junk["count"] == 0 and d_junk["intent"] == "invalid", d_junk["intent"])
    d_gib = ask("asdfghjkl123")
    check("gibberish 'asdfghjkl123' returns 0 rows + invalid", d_gib["count"] == 0 and d_gib["intent"] == "invalid", d_gib["intent"])
finally:
    llm.available = real_available
print("\n== SQL guard ==")
for bad in [
    "DELETE FROM mandi_prices",
    "DROP TABLE mandi_prices",
    "UPDATE mandi_prices SET modal_price=1",
    "SELECT * FROM mandi_prices; DROP TABLE mandi_prices",
    "SELECT * FROM sqlite_master",
    "SELECT * FROM mandi_prices -- comment",
    "PRAGMA table_info(mandi_prices)",
]:
    try:
        validate_sql(bad)
        check(f"reject: {bad[:38]}", False, "was allowed")
    except UnsafeSQLError:
        check(f"reject: {bad[:38]}", True)

safe = validate_sql("SELECT market, modal_price FROM mandi_prices")
check("adds LIMIT", "LIMIT 200" in safe.upper(), safe)
clamped = validate_sql("SELECT market FROM mandi_prices LIMIT 99999")
check("clamps LIMIT", "LIMIT 200" in clamped.upper(), clamped)
allowed = validate_sql("SELECT state, AVG(modal_price) AS avg FROM mandi_prices GROUP BY state")
check("allows aggregate", "GROUP BY" in allowed.upper())

res = execute_readonly("SELECT COUNT(*) AS n FROM mandi_prices")
check("read-only executes", res["rows"][0][0] == 924, res["rows"])
check("read-only returns columns", res["columns"] == ["n"], res["columns"])

print("\n== LLM path (mocked provider) ==")
real_available, real_generate = llm.available, llm.generate_sql
real_phrase = llm.phrase_answer
try:
    llm.available = lambda: True
    llm.phrase_answer = lambda q, c, r, fallback: fallback

    llm.generate_sql = lambda q, h=None: {
        "sql": "SELECT market, state, modal_price FROM mandi_prices WHERE LOWER(commodity)='onion' "
               "AND arrival_date='2026-11-04' ORDER BY modal_price ASC LIMIT 3",
        "rationale": "cheapest onion markets",
    }
    d = ask("cheapest onions please")
    check("llm engine used", d["engine"] == "llm", d["engine"])
    check("llm sql executed", d["count"] == 3, d["count"])
    check("llm chart inferred", d.get("chart_type") == "bar", d.get("chart_type"))
    check("llm rationale returned", d.get("rationale") == "cheapest onion markets")

    llm.generate_sql = lambda q, h=None: {"sql": "DROP TABLE mandi_prices", "rationale": "bad"}
    d = ask("Which market has the cheapest onion price?")
    check("unsafe LLM sql falls back", d["engine"] == "rules" and d["intent"] == "cheapest", d["engine"])

    def boom(q, h=None):
        raise RuntimeError("provider down")
    llm.generate_sql = boom
    d = ask("What is the tomato price in Chennai?")
    check("provider failure falls back", d["engine"] == "rules" and d["intent"] == "price", d["engine"])
finally:
    llm.available, llm.generate_sql, llm.phrase_answer = real_available, real_generate, real_phrase

print("\n== status ==")
s = client.get("/api/status").json()
check("status shape", {"records", "latest_date", "llm_available", "voice"} <= set(s), s)
check("status record count", s["records"] == 924, s["records"])
check("llm status matches key config", s["llm_available"] is bool(settings.LLM_API_KEY), s)
if settings.llm_available():
    print(f"\n== Live LLM path ({settings.LLM_PROVIDER} / {settings.LLM_MODEL}) ==")
    live_d = ask("Which market has the cheapest onion price?")
    check("live llm engine used", live_d["engine"] == "llm", live_d["engine"])
    check("live llm returns 5 rows", live_d["count"] == 5, live_d["count"])
    check("live llm non-empty answer", len(live_d["answer"]) > 10, live_d["answer"])
    live_tom = ask("Tomato")
    check("live llm bare 'Tomato' returns rows", live_tom["count"] > 0 and len(live_tom.get("chart", [])) > 0, live_tom["count"])
    live_cloth = ask("Cloth")
    check("live llm invalid 'Cloth' returns 0 rows + supported list", live_cloth["count"] == 0 and "Tomato" in (live_cloth.get("supported_commodities") or []), live_cloth["answer"])
    live_junk = ask("@#$%^&*!")
    check("live llm junk '@#$%^&*!' rejected with 0 rows", live_junk["count"] == 0 and live_junk["intent"] == "invalid", live_junk["intent"])
print("\n== Speech-to-Text (/api/transcribe) ==")
check("empty audio returns 400", client.post("/api/transcribe", content=b"").status_code == 400)
real_transcribe = llm.transcribe_audio
try:
    llm.transcribe_audio = lambda b, filename="speech.webm", content_type="audio/webm": "What is the tomato price in Chennai?"
    tr = client.post("/api/transcribe", content=b"RIFFmock", headers={"Content-Type": "audio/wav", "X-Audio-Filename": "speech.wav"})
    check("mocked transcribe 200", tr.status_code == 200 and tr.json()["text"] == "What is the tomato price in Chennai?", tr.text)
finally:
    llm.transcribe_audio = real_transcribe

if settings.stt_available() and sys.platform == "win32":
    import subprocess
    import tempfile
    from pathlib import Path
    wav_path = Path(tempfile.gettempdir()) / "dg_test_stt.wav"
    ps_cmd = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{wav_path}'); "
        "$s.Speak('Which market has the cheapest onion price in Tamil Nadu?'); "
        "$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True)
    tr_live = client.post(
        "/api/transcribe",
        content=wav_path.read_bytes(),
        headers={"Content-Type": "audio/wav", "X-Audio-Filename": "speech.wav"},
    )
    txt = tr_live.json().get("text", "").lower() if tr_live.status_code == 200 else ""
    check("live groq whisper stt", tr_live.status_code == 200 and "onion" in txt and "tamil nadu" in txt, tr_live.text)
m = client.get("/api/meta").json()
check("meta date range", m["date_range"] == ["2026-10-15", "2026-11-04"], m["date_range"])
check("meta days", m["days"] == 21, m["days"])

print("\n" + ("ALL V2 CHECKS PASS" if not failures else f"{len(failures)} FAILURES: {failures}"))
sys.exit(1 if failures else 0)
