import csv
import datetime as dt
import time

from config import (
    ENABLE_SWING_ALERTS,
    LOG_FILE,
    SWING_ALERT_COOLDOWN_SEC,
)
from swing_scanner import score_swing_setup, format_swing_alert


SWING_ALERT_CACHE = {}


def log_swing_alert(ticker, setup, tech):
    fields = [
        "timestamp", "ticker", "alert_type", "direction", "entry_mode", "score",
        "ml_probability", "entry", "stop", "target", "risk_reward", "hold_days",
        "price", "dma20", "dma50", "dma200", "atr14", "reasons",
    ]
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

    now = time.time()
    last_alert = SWING_ALERT_CACHE.get(ticker)

    if last_alert and (now - last_alert) < SWING_ALERT_COOLDOWN_SEC:
        remaining = int((SWING_ALERT_COOLDOWN_SEC - (now - last_alert)) / 60)
        print(f"{ticker}: swing cooldown active ({remaining}m remaining)")
        return None

    setup = score_swing_setup(tech)
    
    from ai_reasoning_engine import build_reasoning_report

    reasoning = build_reasoning_report(
        ticker=ticker,
        setup=setup,
        tech=tech,
        bot=bot,
        trade_type="SWING",
    )

    setup["ai_reasoning"] = reasoning
    setup["score"] = reasoning["final_score"]
    setup["decision"] = reasoning["decision"]

    if not setup:
        return None

    try:
        from ml_sklearn_model import adjust_score_with_logistic
        adjusted, prob, _ = adjust_score_with_logistic(tech, setup.get("score", 0))
        setup["score"] = adjusted
        setup["ml_probability"] = prob
        setup["ai_reasoning"] = reasoning_report
    except Exception as e:
        print(f"{ticker}: swing ML skipped: {e}")

    try:
        bot.send_telegram_msg(format_swing_alert(ticker, setup))
        SWING_ALERT_CACHE[ticker] = now
    except Exception as e:
        print(f"{ticker}: swing telegram error: {e}")

    log_swing_alert(ticker, setup, tech)
    return setup
