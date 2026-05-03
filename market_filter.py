from market_data import get_stock_data, compute_indicators


def get_market_bias(symbol: str = "SPY") -> dict:
    """Return broad-market bias using SPY 6-month daily trend."""
    df = compute_indicators(get_stock_data(symbol))
    latest = df.iloc[-1]

    bullish = latest.Close > latest.EMA8 > latest.EMA21 > latest.EMA50
    bearish = latest.Close < latest.EMA8 < latest.EMA21 < latest.EMA50

    if bullish:
        bias = "BULLISH"
    elif bearish:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    return {
        "symbol": symbol,
        "bias": bias,
        "price": float(latest.Close),
        "ema8": float(latest.EMA8),
        "ema21": float(latest.EMA21),
        "ema50": float(latest.EMA50),
        "rel_volume": float(latest.RelVol),
    }


def market_allows_setup(stock_signal: str, market_bias: str) -> tuple[bool, str]:
    """Avoid taking stock setups against the broad-market direction."""
    long_signals = {"BULLISH BREAKOUT", "UPTREND"}
    weak_signals = {"BEARISH BREAKDOWN", "DOWNTREND"}

    if market_bias == "BULLISH" and stock_signal in long_signals:
        return True, "SPY bias supports bullish setup"

    if market_bias == "BEARISH" and stock_signal in weak_signals:
        return True, "SPY bias supports bearish setup"

    if market_bias == "NEUTRAL":
        return False, "SPY is neutral/choppy; wait for stronger market direction"

    return False, f"SPY bias {market_bias} conflicts with stock signal {stock_signal}"
