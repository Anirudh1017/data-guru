"""Environment-driven settings. Every V2 feature degrades gracefully when unset."""
import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).parent
load_dotenv(BACKEND_DIR / ".env", override=True)

DB_PATH = Path(os.getenv("DB_PATH", str(BACKEND_DIR / "data_guru.db")))

# --- data.gov.in (live mandi data) ---
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY", "").strip()
DATA_GOV_RESOURCE = os.getenv(
    "DATA_GOV_RESOURCE", "9ef84268-d588-465a-a308-a864a43d0070"
)
DATA_GOV_BASE = os.getenv("DATA_GOV_BASE", "https://api.data.gov.in/resource")

# --- LLM (OpenAI-compatible: OpenAI, Groq, Together, OpenRouter, Ollama, Gemini-compat) ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_SUMMARY = os.getenv("LLM_SUMMARY", "true").strip().lower() in ("1", "true", "yes")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))

# --- Speech-to-Text (Groq / OpenAI Whisper-compatible) ---
STT_API_KEY = os.getenv("STT_API_KEY", LLM_API_KEY).strip()
STT_BASE_URL = os.getenv("STT_BASE_URL", "").strip()
STT_MODEL = os.getenv("STT_MODEL", "whisper-large-v3-turbo").strip()
# Sensible defaults per provider, all OpenAI-compatible endpoints.
_PROVIDER_DEFAULTS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    "together": ("https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-4o-mini"),
    "ollama": ("http://127.0.0.1:11434/v1", "llama3.1"),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-2.0-flash",
    ),
}

def _resolve_llm():
    base, model = _PROVIDER_DEFAULTS.get(LLM_PROVIDER, _PROVIDER_DEFAULTS["openai"])
    return LLM_BASE_URL or base, LLM_MODEL or model

LLM_BASE_URL, LLM_MODEL = _resolve_llm()
if not STT_BASE_URL:
    STT_BASE_URL = (
        "https://api.groq.com/openai/v1"
        if (LLM_PROVIDER == "groq" or STT_API_KEY.startswith("gsk_"))
        else LLM_BASE_URL
    )

def llm_available() -> bool:
    """Ollama runs locally and needs no key; every hosted provider needs one."""
    if LLM_PROVIDER == "ollama":
        return True
    return bool(LLM_API_KEY)


def data_available() -> bool:
    return bool(DATA_GOV_API_KEY)
def stt_available() -> bool:
    return bool(STT_API_KEY)


def public_config() -> dict:
    return {
        "llm_available": llm_available(),
        "llm_provider": LLM_PROVIDER if llm_available() else None,
        "llm_model": LLM_MODEL if llm_available() else None,
        "stt_available": stt_available(),
        "stt_model": STT_MODEL if stt_available() else None,
        "data_sync_available": data_available(),
        "voice": "groq" if stt_available() else "browser",
    }
