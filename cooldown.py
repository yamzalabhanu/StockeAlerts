from datetime import datetime, timedelta

COOLDOWN_MINUTES = 15
cooldown_store = {}


def is_in_cooldown(symbol: str, signal: str) -> bool:
    key = f"{symbol}_{signal}"
    if key not in cooldown_store:
        return False

    last_time = cooldown_store[key]
    return datetime.utcnow() - last_time < timedelta(minutes=COOLDOWN_MINUTES)


def update_cooldown(symbol: str, signal: str):
    key = f"{symbol}_{signal}"
    cooldown_store[key] = datetime.utcnow()
