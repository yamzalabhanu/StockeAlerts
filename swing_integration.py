import csv
import datetime as dt
import re
import time

from bot_utils import safe_float

from config import (
    ENABLE_SWING_ALERTS,
    LOG_FILE,
    SWING_ALERT_COOLDOWN_SEC,
    SWING_HOLD_DAYS_MAX,
)
from swing_scanner import score_swing_setup, format_swing_alert
from ai_reasoning_engine import build_reasoning_report
from setup_filters import PASS, WARNING
from outcome_tracker import track_outcome
from performance_learning import calibrate_confidence, priority_bonus, setup_structure_key

SWING_ALERT_CACHE = {}


SWING_MIN_BENCHMARK_RR = 2.0
SWING_REQUIRED_DECISION = "A+"
SWING_REQUIRED_COMPOSITE_SCORE = 100
SWING_REQUIRED_REGIME = "TRENDING_BULL"
SWING_REQUIRED_EXECUTION = WARNING
SWING_ALLOWED_SETUP_FILTERS = {PASS, WARNING}
SWING_REQUIRED_CHART_STRUCTURE = "ELITE"
SWING_REQUIRED_MTF_STRUCTURE = "STRONG_ALIGNMENT"


def meets_swing_benchmark(setup, reasoning):
    """Return True only for swing alerts matching the required elite criteria."""
    setup = setup or {}
    reasoning = reasoning or {}

    if reasoning.get("decision") != SWING_REQUIRED_DECISION:
        return False

    composite_score = safe_float(reasoning.get("final_score") or setup.get("score"))
    if composite_score != SWING_REQUIRED_COMPOSITE_SCORE:
        return False

    if safe_float(setup.get("risk_reward")) < SWING_MIN_BENCHMARK_RR:
        return False

    if reasoning.get("reject_reasons"):
        return False

    regime = (reasoning.get("regime") or {}).get("regime")
    if regime != SWING_REQUIRED_REGIME:
        return False

    mtf_structure = (reasoning.get("mtf") or {}).get("structure")
    if mtf_structure != SWING_REQUIRED_MTF_STRUCTURE:
        return False

    execution = (reasoning.get("execution") or {}).get("quality")
    if execution != SWING_REQUIRED_EXECUTION:
        return False

    setup_filter = (reasoning.get("setup_quality") or {}).get("status")
    if setup_filter not in SWING_ALLOWED_SETUP_FILTERS:
        return False

    chart_structure = (reasoning.get("vision") or {}).get("quality")
    if chart_structure != SWING_REQUIRED_CHART_STRUCTURE:
        return False

    return setup.get("direction") in {"CALL", "PUT"}


def _hold_days_to_horizon_minutes(hold_days, default_days=SWING_HOLD_DAYS_MAX):
    """Convert a swing hold-days value into an outcome-tracking horizon.

    Swing alerts display hold windows such as ``"2-10"`` days. For outcome
    tracking, use the far end of that range so the trade has the full advertised
    holding window to reach its stop or target.
    """
    if hold_days is None or hold_days == "":
        days = default_days
    elif isinstance(hold_days, (int, float)):
        days = hold_days
    else:
        day_values = re.findall(r"\d+(?:\.\d+)?", str(hold_days))
        days = float(day_values[-1]) if day_values else default_days

    if days <= 0:
        days = default_days

    return int(days * 24 * 60)


def log_swing_alert(ticker, setup, tech):
    setup = setup or {}
    tech = tech or {}

    fields = [
        "timestamp", "ticker", "alert_type", "direction", "entry_mode", "score",
        "ml_probability", "entry", "stop", "target", "risk_reward", "hold_days",
        "price", "dma20", "dma50", "dma200", "atr14", "setup_key", "learning_key", "learning_win_rate", "forecast_accuracy", "priority_bonus", "reasons",
    ]

    reasoning = setup.get("ai_reasoning") or {}
    learning_context = reasoning.get("learning_context") or {}
    learning_confidence = reasoning.get("learning_confidence") or {}
    learning_stats = learning_confidence.get("learning_stats") or {}
    setup_key = learning_context.get("setup_key") or setup_structure_key({"alert_type": "SWING", "entry_mode": "SWING", "direction": setup.get("direction")})

    row = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ticker": ticker,
        "alert_type": "SWING",
        "direction": setup.get("direction"),
        "entry_mode": "SWING",
        "score": setup.get("score"),
        "ml_probability": setup.get("ml_probability"),
        "entry": setup.get("entry"),
        "stop": setup.get("stop"),
        "target": setup.get("target"),
        "risk_reward": setup.get("risk_reward"),
        "hold_days": setup.get("hold_days"),
        "price": tech.get("price"),
        "dma20": tech.get("dma20"),
        "dma50": tech.get("dma50"),
        "dma200": tech.get("dma200"),
        "atr14": tech.get("atr14"),
        "setup_key": setup_key,
        "learning_key": learning_confidence.get("learning_key"),
        "learning_win_rate": learning_stats.get("win_rate"),
        "forecast_accuracy": learning_stats.get("forecast_accuracy"),
        "priority_bonus": reasoning.get("priority_bonus"),
        "reasons": ", ".join(setup.get("reasons", [])),
    }

    try:
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writerow(row)
    except Exception as e:
        print(f"{ticker}: swing log error: {e}")


def process_swing_candidate(bot, ticker, tech):
    if not ENABLE_SWING_ALERTS:
        return None

    tech = tech or {}

    now = time.time()
    last_alert = SWING_ALERT_CACHE.get(ticker)

    if last_alert and (now - last_alert) < SWING_ALERT_COOLDOWN_SEC:
        remaining = int((SWING_ALERT_COOLDOWN_SEC - (now - last_alert)) / 60)
        print(f"{ticker}: swing cooldown active ({remaining}m remaining)")
        return None

    try:
        setup = score_swing_setup(tech)
    except Exception as e:
        print(f"{ticker}: swing setup scoring error: {e}")
        return None

    if setup is None:
        return None

    if not isinstance(setup, dict):
        print(f"{ticker}: invalid swing setup object")

        return None

    try:
        reasoning = build_reasoning_report(
            ticker=ticker,
            setup=setup,
            tech=tech,
            bot=bot,
            trade_type="SWING",
        ) or {}

        if not isinstance(reasoning, dict):
            reasoning = {}

        setup["ai_reasoning"] = reasoning
        setup["score"] = reasoning.get("final_score", setup.get("score", 0))
        setup["decision"] = reasoning.get("decision", setup.get("tier", "WATCH"))

        if not meets_swing_benchmark(setup, reasoning):
            print(
                f"{ticker}: swing benchmark rejected "
                f"({setup.get('direction')} {setup.get('decision')} score {setup.get('score')})"
            )
            return None
        learning_context = reasoning.get("learning_context") or {"alert_type": "SWING", "entry_mode": "SWING", "direction": setup.get("direction")}
        confidence_learning = calibrate_confidence(setup.get("score", 0), learning_context)
        setup["calibrated_confidence"] = confidence_learning.get("calibrated_confidence")
        setup["confidence_adjustment"] = confidence_learning.get("confidence_adjustment")
        setup["historical_priority_bonus"] = priority_bonus(learning_context)

    except Exception as e:
        print(f"{ticker}: reasoning engine error: {e}")
        setup["ai_reasoning"] = {}

    try:
        from ml_sklearn_model import adjust_score_with_logistic

        adjusted, prob, model_info = adjust_score_with_logistic(
            tech,
            setup.get("score", 0),
        )

        setup["score"] = adjusted
        setup["ml_probability"] = prob

        setup["ml_model_info"] = model_info

    except Exception as e:
        print(f"{ticker}: swing ML skipped: {e}")

    try:
        reasoning = setup.get("ai_reasoning") or {}
        learning_context = reasoning.get("learning_context") or {"alert_type": "SWING", "entry_mode": "SWING", "direction": setup.get("direction")}
        setup["score"] = round(max(0, min(100, float(setup.get("score", 0) or 0) + priority_bonus(learning_context))), 2)
    except Exception as e:
        print(f"{ticker}: swing historical prioritization skipped: {e}")

    telegram_sent = False
    try:
        message = format_swing_alert(ticker, setup)
        telegram_sent = bool(bot.send_telegram_msg(message))
        if telegram_sent:
            SWING_ALERT_CACHE[ticker] = now
        else:
            print(f"{ticker}: swing telegram send failed; alert not counted as sent")
    except Exception as e:
        print(f"{ticker}: swing telegram error: {e}")

    if not telegram_sent:
        return None

    log_swing_alert(ticker, setup, tech)

    try:
        alert_time = dt.datetime.now(dt.timezone.utc).isoformat()
        reasoning = setup.get("ai_reasoning") or {}
        learning_context = reasoning.get("learning_context") or {}
        track_outcome(
            ticker=ticker,
            direction=setup.get("direction"),
            entry=float(setup.get("entry")),
            stop=float(setup.get("stop")),
            target=float(setup.get("target")),
            alert_time_iso=alert_time,
            alert_type="SWING",
            entry_mode="SWING",
            horizon_minutes=_hold_days_to_horizon_minutes(setup.get("hold_days")),
            setup_context={
                "setup_key": learning_context.get("setup_key"),
                "market_regime": (reasoning.get("regime") or {}).get("regime"),
                "mtf_structure": (reasoning.get("mtf") or {}).get("structure"),
                "chart_structure": (reasoning.get("vision") or {}).get("quality"),
                "ai_confidence": setup.get("score"),
                "calibrated_confidence": setup.get("calibrated_confidence"),
                "score": setup.get("score"),
            },
        )
    except Exception as e:
        print(f"{ticker}: swing outcome tracking skipped: {e}")

    return setup
