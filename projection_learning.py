# projection_learning.py

LEARNING_FILE = "projection_learning.json"


def record_projection(ticker, projection, entry_price):
    return {
        "ticker": ticker,
        "direction": projection.get("direction"),
        "confidence": projection.get("confidence"),
        "entry_price": entry_price,
    }


def retrain_confidence_engine(history=None):
    history = history or []

    total = len(history)

    if total == 0:
        return {
            "status": "no_data",
            "samples": 0,
        }

    return {
        "status": "trained",
        "samples": total,
    }
