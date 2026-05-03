MAX_TRADES = 3
RISK_PER_TRADE = 0.01

active_trades = []


def can_open_trade():
    return len(active_trades) < MAX_TRADES


def calculate_position(account_size, entry, stop):
    risk = abs(entry - stop)
    if risk == 0:
        return 0
    position_size = (account_size * RISK_PER_TRADE) / risk
    return round(position_size)


def add_trade(symbol):
    active_trades.append(symbol)


def remove_trade(symbol):
    if symbol in active_trades:
        active_trades.remove(symbol)
