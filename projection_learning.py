# projection_learning.py

LEARNING_FILE = "projection_learning.json"


def record_projection(ticker, projection, entry_price):
    projection = projection or {}

    return {
        "ticker": ticker,
        "direction": projection.get("direction"),
        "confidence": projection.get("confidence"),
        "projected_move_pct": projection.get("projected_move_pct"),
        "expected_price_range": projection.get("expected_price_range"),
        "entry_price": entry_price,
    }


def compare_projection_vs_actual(entry_price, actual_price, direction):
    if not entry_price or not actual_price:
        return {
            "success": False,
            "move_pct": 0,
        }

    move_pct = round(((actual_price - entry_price) / entry_price) * 100, 2)

    success = False

    if direction == "BULLISH" and actual_price > entry_price:
        success = True

    if direction == "BEARISH" and actual_price < entry_price:
        success = True

    return {
        "success": success,
        "move_pct": move_pct,
    }


def retrain_confidence_engine(history=None):
    history = history or []

    total = len(history)

    if total == 0:
        return {
            "status": "no_data",
            "samples": 0,
        }

    wins = 0

    for item in history:
        if item.get("success"):
            wins += 1

    accuracy = round((wins / total) * 100, 2)

    return {
        "status": "trained",
        "samples": total,
        "accuracy_pct": accuracy,
    }
