import csv
import datetime as dt
from config import ENABLE_SWING_ALERTS, LOG_FILE
from swing_scanner import score_swing_setup, format_swing_alert


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

    setup = score_swing_setup(tech)
    if not setup:
        return None

    try:
        from ml_sklearn_model import adjust_score_with_logistic
        adjusted, prob, _ = adjust_score_with_logistic(tech, setup.get("score", 0))
        setup["score"] = adjusted
        setup["ml_probability"] = prob
    except Exception as e:
        print(f"{ticker}: swing ML skipped: {e}")

    try:
        bot.send_telegram_msg(format_swing_alert(ticker, setup))
    except Exception as e:
        print(f"{ticker}: swing telegram error: {e}")

    log_swing_alert(ticker, setup, tech)
    return setup
