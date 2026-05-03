from market_data import get_stock_data


def _add_intraday_indicators(df):
    df = df.copy()
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    df["VWAP"] = (typical * df["Volume"]).cumsum() / df["Volume"].cumsum()
    df["Vol20"] = df["Volume"].rolling(20).mean()
    df["RelVol"] = df["Volume"] / df["Vol20"]
    return df.dropna()


def _timeframe_state(symbol: str, interval: str, bullish: bool) -> dict:
    df = _add_intraday_indicators(get_stock_data(symbol, period="5d", interval=interval))
    if df.empty:
        return {"interval": interval, "ok": False, "reason": "No data"}

    latest = df.iloc[-1]
    price = float(latest.Close)

    if bullish:
        aligned = price > latest.VWAP and latest.EMA9 > latest.EMA21 > latest.EMA50
        reason = "bullish aligned" if aligned else "bullish MTF alignment missing"
    else:
        aligned = price < latest.VWAP and latest.EMA9 < latest.EMA21 < latest.EMA50
        reason = "bearish aligned" if aligned else "bearish MTF alignment missing"

    return {
        "interval": interval,
        "ok": bool(aligned),
        "price": round(price, 2),
        "ema9": round(float(latest.EMA9), 2),
        "ema21": round(float(latest.EMA21), 2),
        "ema50": round(float(latest.EMA50), 2),
        "vwap": round(float(latest.VWAP), 2),
        "rel_volume": round(float(latest.RelVol), 2),
        "reason": reason,
    }


def mtf_confirmation(symbol: str, analysis: dict, strict: bool = True) -> tuple[bool, dict]:
    """Confirm setup across 5m, 15m, and 1h trend alignment."""
    signal = analysis.get("signal", "")
    bullish = "BULLISH" in signal or "UPTREND" in signal
    bearish = "BEARISH" in signal or "DOWNTREND" in signal

    if not bullish and not bearish:
        return False, {"reason": "No directional signal"}

    states = [
        _timeframe_state(symbol, "5m", bullish),
        _timeframe_state(symbol, "15m", bullish),
        _timeframe_state(symbol, "60m", bullish),
    ]

    passed = sum(1 for s in states if s.get("ok"))
    required = 3 if strict else 2
    approved = passed >= required

    return approved, {
        "approved": approved,
        "passed": passed,
        "required": required,
        "mode": "strict" if strict else "soft",
        "states": states,
        "reason": "MTF aligned" if approved else "MTF alignment failed",
    }
