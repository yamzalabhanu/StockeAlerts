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
    """Avoid true counter-trend trades, but do not block neutral/watchlist setups.

    Previous logic rejected SIDEWAYS / EARLY WATCH signals during a bullish SPY regime,
    which removed many valid watch/retest setups. This filter now only blocks clear
    bearish setups in a bullish tape and clear bullish setups in a bearish tape.
    """
    signal = (stock_signal or "").upper()

    bullish_signal = any(token in signal for token in ["BULLISH", "UPTREND"])
    bearish_signal = any(token in signal for token in ["BEARISH", "DOWNTREND", "BREAKDOWN"])
    neutral_signal = any(token in signal for token in ["SIDEWAYS", "WATCH"])

    if market_bias == "BULLISH":
        if bearish_signal:
            return False, f"SPY bias {market_bias} conflicts with bearish stock signal {stock_signal}"
        return True, "SPY bullish; allowing bullish/neutral/early-watch setup"

    if market_bias == "BEARISH":
        if bullish_signal:
            return False, f"SPY bias {market_bias} conflicts with bullish stock signal {stock_signal}"
        return True, "SPY bearish; allowing bearish/neutral setup"

    if market_bias == "NEUTRAL":
        if neutral_signal:
            return False, "SPY is neutral/choppy and stock setup is also neutral"
        return True, "SPY neutral; allowing directional stock setup with other confirmations"

    return True, "Market filter passed"
