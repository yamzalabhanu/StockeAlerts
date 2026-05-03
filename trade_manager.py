from storage import load_results, update_trade_outcome
from market_data import get_stock_data, compute_indicators


def manage_open_trades():
    """Automatically close open trades when stop or target is reached."""
    trades = load_results()
    updated = []

    for trade in trades:
        if trade.get("status") != "OPEN":
            continue

        symbol = trade.get("symbol")
        if not symbol:
            continue

        price = float(compute_indicators(get_stock_data(symbol, period="5d", interval="1d")).iloc[-1].Close)
        stop = trade.get("stop")
        target = trade.get("target")
        direction = trade.get("direction", "LONG")

        if stop is None or target is None:
            continue

        stop = float(stop)
        target = float(target)

        if direction == "LONG":
            if price <= stop:
                updated.append(update_trade_outcome(trade["id"], price, "LOSS"))
            elif price >= target:
                updated.append(update_trade_outcome(trade["id"], price, "WIN"))
        else:
            if price >= stop:
                updated.append(update_trade_outcome(trade["id"], price, "LOSS"))
            elif price <= target:
                updated.append(update_trade_outcome(trade["id"], price, "WIN"))

    return updated
