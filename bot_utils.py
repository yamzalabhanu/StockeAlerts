import json
import re


_WORD_TO_NUMBER = {
    "VERY HIGH": 95,
    "HIGH": 85,
    "MEDIUM": 60,
    "MODERATE": 60,
    "LOW": 40,
    "VERY LOW": 20,
    "POOR": 20,
}


def safe_float(value, default=0.0):
    """Safely convert numeric or word-based LLM values to float.

    Handles common LLM outputs like "high", "medium", "low", "2:1", and "2.1x".
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return float(value)

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        raw = value.strip()
        upper = raw.upper()

        if upper in _WORD_TO_NUMBER:
            return float(_WORD_TO_NUMBER[upper])

        # Convert common risk/reward forms such as "2:1", "2.3x", "$123.45".
        cleaned = raw.replace("$", "").replace(",", "").replace("x", "").replace("X", "")
        if ":" in cleaned:
            cleaned = cleaned.split(":", 1)[0]

        try:
            return float(cleaned)
        except Exception:
            return default

    return default


def safe_int(value, default=0):
    try:
        return int(round(safe_float(value, default)))
    except Exception:
        return default


def safe_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "confirmed"}
    return bool(value)


def fmt_price(value):
    return "N/A" if value is None else f"{safe_float(value):.2f}"


def pct_diff(a, b):
    if a is None or b is None:
        return None

    a = safe_float(a)
    b = safe_float(b)

    if b == 0:
        return None

    return ((a - b) / b) * 100


def extract_gpt_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass

    try:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass

    return {
        "verdict": "WAIT",
        "confidence": 50,
        "entry": None,
        "stop": None,
        "target": None,
        "risk_reward": 0,
        "setup_quality": "LOW",
        "entry_timing": "UNKNOWN",
        "retest_confirmed": False,
        "late_breakout_risk": True,
        "reason": str(text)[:300],
    }


def normalize_ai_response(data):
    if not isinstance(data, dict):
        data = {}

    data["verdict"] = str(data.get("verdict", "WAIT")).upper()
    if data["verdict"] not in {"BUY", "WAIT"}:
        data["verdict"] = "WAIT"

    data["confidence"] = max(0, min(safe_int(data.get("confidence", 50), 50), 100))
    data["reason"] = str(data.get("reason", ""))[:500]

    data["setup_quality"] = str(data.get("setup_quality", "LOW")).upper()
    if data["setup_quality"] not in {"A+", "A", "B", "LOW"}:
        # Map word-like quality if AI returns confidence wording here too.
        quality_score = safe_int(data["setup_quality"], 0)
        if quality_score >= 90:
            data["setup_quality"] = "A+"
        elif quality_score >= 80:
            data["setup_quality"] = "A"
        elif quality_score >= 65:
            data["setup_quality"] = "B"
        else:
            data["setup_quality"] = "LOW"

    data["entry_timing"] = str(data.get("entry_timing", "UNKNOWN")).upper()
    if data["entry_timing"] not in {"EARLY", "IDEAL", "LATE", "CHOP", "UNKNOWN"}:
        data["entry_timing"] = "UNKNOWN"

    data["entry"] = safe_float(data.get("entry"), None)
    data["stop"] = safe_float(data.get("stop"), None)
    data["target"] = safe_float(data.get("target"), None)
    data["risk_reward"] = safe_float(data.get("risk_reward"), 0)

    data["retest_confirmed"] = safe_bool(data.get("retest_confirmed", False), False)
    data["late_breakout_risk"] = safe_bool(data.get("late_breakout_risk", True), True)

    return data
