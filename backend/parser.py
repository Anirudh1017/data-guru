"""Rule-based NL parser. Handles V1 intents plus trends and follow-ups — no API key."""
import re
from db import get_conn

COMMODITY_ALIASES = {
    "tomato": "Tomato", "tomatoes": "Tomato",
    "onion": "Onion", "onions": "Onion",
    "potato": "Potato", "potatoes": "Potato",
    "wheat": "Wheat", "rice": "Rice", "paddy": "Rice",
    "corn": "Corn", "maize": "Corn",
    "banana": "Banana", "bananas": "Banana",
    "apple": "Apple", "apples": "Apple",
    "grape": "Grapes", "grapes": "Grapes",
    "cabbage": "Cabbage", "cauliflower": "Cauliflower",
    "brinjal": "Brinjal", "eggplant": "Brinjal",
    "lady finger": "Okra", "okra": "Okra", "bhindi": "Okra",
    "carrot": "Carrot", "carrots": "Carrot",
    "chili": "Green Chilli", "chilli": "Green Chilli", "chillies": "Green Chilli",
    "coconut": "Coconut", "turmeric": "Turmeric",
    "groundnut": "Groundnut", "sugarcane": "Sugarcane",
}

CHEAPEST_WORDS = ("cheapest", "lowest", "least expensive", "minimum", "top five", "top 5")
COMPARE_WORDS = ("compare", "comparison", " vs ", "versus", "difference between")
TREND_WORDS = ("trend", "over time", "history", "historical", "last week", "last month",
               "past week", "past month", "movement", "moved", "change over", "day by day")
FOLLOWUP_CUES = ("and ", "what about", "how about", "there", "same", "those", "that one", "in kerala", "in tamil")
VISUAL_WORDS = ("visualize", "visualise", "visualization", "visualisation", "chart", "graph", "plot", "diagram")

STOP_WORDS = {
    "what", "is", "are", "the", "price", "prices", "cost", "rate", "rates", "of", "in",
    "at", "for", "to", "from", "and", "or", "vs", "versus", "compare", "comparison",
    "difference", "between", "which", "market", "markets", "mandi", "mandis", "has",
    "have", "lowest", "cheapest", "highest", "expensive", "minimum", "maximum", "modal",
    "average", "avg", "top", "five", "how", "much", "moved", "movement", "trend",
    "trends", "over", "time", "last", "past", "two", "weeks", "week", "month", "days",
    "day", "by", "history", "historical", "show", "me", "tell", "give", "find", "search",
    "list", "all", "today", "current", "now", "latest", "state", "states", "district",
    "districts", "india", "indian", "agricultural", "agriculture", "commodity", "commodities",
    "please", "about", "there", "same", "those", "that", "one", "per", "quintal", "rupees",
    "kg", "kgs", "kilogram", "kilograms", "kilo", "kilos", "gm", "gms", "gram", "grams",
    "visualize", "visualise", "visualization", "visualisation", "chart", "graph", "plot",
    "diagram", "convert", "converted", "unit", "units",
}


def parse_requested_unit(q: str) -> tuple[str | None, float]:
    """Detect kg or gram/gms unit requests and optional numeric quantity."""
    m_gm = re.search(r"(?:(\d+(?:\.\d+)?)\s*)?\b(gms?|grams?)\b", q)
    if m_gm:
        qty = float(m_gm.group(1)) if m_gm.group(1) else 100.0
        return ("gm", qty)
    m_kg = re.search(r"(?:(\d+(?:\.\d+)?)\s*)?\b(kgs?|kilograms?|kilos?)\b", q)
    if m_kg:
        qty = float(m_kg.group(1)) if m_kg.group(1) else 1.0
        return ("kg", qty)
    return (None, 1.0)

def is_junk_query(question: str) -> bool:
    """Detect symbol-only, numeric-only, or keyboard-mash gibberish."""
    s = question.strip()
    if not s:
        return True
    letters = [ch for ch in s if ch.isalpha()]
    if len(letters) < 2:
        return True
    alnum = [ch for ch in s if ch.isalnum()]
    # Mostly punctuation/symbols
    if len(letters) / max(len(s.replace(" ", "")), 1) < 0.4:
        return True
    # Keyboard mash / gibberish: no vowels in alpha words or long consonant runs
    words = re.findall(r"[a-zA-Z]+", s.lower())
    if not words:
        return True
    vowels = set("aeiou")
    has_real_word = False
    for w in words:
        w_vowels = sum(1 for c in w if c in vowels)
        # Keyboard-row smash like 'asdfghjkl' or consonant cluster > 5 chars
        if re.search(r"[bcdfghjklmnpqrstvwxyz]{5,}", w):
            continue
        if len(w) >= 2 and w_vowels > 0:
            has_real_word = True
    if not has_real_word:
        return True
    # Single token mixing letters and trailing digits like 'asdfghjkl123'
    if len(words) == 1 and len(alnum) > len(letters) and words[0] not in COMMODITY_ALIASES and words[0] not in STOP_WORDS:
        return True
    return False

def _distinct(column: str) -> list[str]:
    try:
        with get_conn() as conn:
            return [
                r[0]
                for r in conn.execute(
                    f"SELECT DISTINCT {column} FROM mandi_prices WHERE {column} IS NOT NULL ORDER BY {column}"
                )
            ]
    except Exception:
        return []


def _match_values(q: str, values: list[str]) -> list[str]:
    """Longest-first so 'Tamil Nadu' wins over a stray 'Nadu'."""
    found = []
    for value in sorted(values, key=len, reverse=True):
        if value.lower() in q and value not in found:
            found.append(value)
    return found


def parse(question: str, history: list[dict] | None = None) -> dict:
    q = question.lower().strip()
    junk = is_junk_query(question)
    commodity = None
    for alias in sorted(COMMODITY_ALIASES, key=len, reverse=True):
        if re.search(r"\b" + re.escape(alias) + r"\b", q):
            commodity = COMMODITY_ALIASES[alias]
            break

    states = _match_values(q, _distinct("state"))
    districts = _match_values(q, _distinct("district"))
    markets = _match_values(q, _distinct("market"))
    requested_unit, unit_qty = parse_requested_unit(q)
    wants_visual = any(w in q for w in VISUAL_WORDS)

    intent = "search"
    intent_explicit = True
    if any(w in q for w in TREND_WORDS):
        intent = "trend"
    elif any(w in q for w in COMPARE_WORDS) and len(states) >= 2:
        intent = "compare"
    elif any(w in q for w in CHEAPEST_WORDS):
        intent = "cheapest"
    elif any(w in q for w in ("price", "cost", "rate", "how much")) or requested_unit is not None:
        intent = "price"
    else:
        intent_explicit = False

    inherited = []
    if history:
        if not commodity:
            for turn in reversed(history):
                prev = turn.get("parsed") or {}
                if prev.get("commodity"):
                    commodity = prev["commodity"]
                    inherited.append("commodity")
                    break
        is_followup = any(cue in q for cue in FOLLOWUP_CUES)
        if is_followup and not intent_explicit:
            for turn in reversed(history):
                prev = turn.get("parsed") or {}
                if prev.get("intent") and prev["intent"] not in ("unknown", "llm_sql", "search"):
                    intent = prev["intent"]
                    inherited.append("intent")
                    break
        if is_followup and not states:
            for turn in reversed(history):
                prev = turn.get("parsed") or {}
                if prev.get("states"):
                    states = prev["states"]
                    inherited.append("states")
                    break

    # Extract unrecognized commodity/subject words when no tracked commodity matched
    unknown_subject = None
    if not junk and not commodity:
        place_words = {
            w
            for item in (*states, *districts, *markets)
            for w in re.findall(r"[a-zA-Z]{3,}", item.lower())
        }
        tokens = [
            w
            for w in re.findall(r"[a-zA-Z]{3,}", q)
            if w not in STOP_WORDS and w not in place_words
        ]
        if tokens:
            unknown_subject = " ".join(tokens[:3]).title()
    return {
        "intent": "invalid" if junk else intent,
        "commodity": commodity,
        "states": states,
        "districts": districts,
        "markets": markets,
        "inherited": inherited,
        "is_junk": junk,
        "unknown_subject": unknown_subject,
        "requested_unit": requested_unit,
        "unit_qty": unit_qty,
        "wants_visual": wants_visual,
    }
