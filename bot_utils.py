import json
import re


def safe_float(value, default=0.0):
    try:
        return float(value) if value is not None else default
    except Exception:
        return default


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
        "reason": text[:300],
    }


def normalize_ai_response(data):
    data["verdict"] = str(data.get("verdict", "WAIT")).upper()
    data["confidence"] = int(float(data.get("confidence", 50)))
    data["reason"] = str(data.get("reason", ""))[:500]
    data["setup_quality"] = str(data.get("setup_quality", "LOW")).upper()
    data["entry_timing"] = str(data.get("entry_timing", "UNKNOWN")).upper()

    data["entry"] = safe_float(data.get("entry"), None)
    data["stop"] = safe_float(data.get("stop"), None)
    data["target"] = safe_float(data.get("target"), None)
    data["risk_reward"] = safe_float(data.get("risk_reward"), 0)

    data["retest_confirmed"] = bool(data.get("retest_confirmed", False))
    data["late_breakout_risk"] = bool(data.get("late_breakout_risk", True))

    return data
