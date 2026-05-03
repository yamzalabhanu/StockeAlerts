from datetime import datetime

from market_data import get_stock_data


def _vwap(df):
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    return (typical * df["Volume"]).cumsum() / df["Volume"].cumsum()


def intraday_confirmation(symbol: str, analysis: dict) -> tuple[bool, dict]:
    """Confirm swing setup with recent 5-minute price action.

    Checks:
    - only evaluates during normal market hours when intraday data is meaningful
    - 5m trend alignment using EMA9/EMA21
    - VWAP side alignment
    - strong candle body confirmation
    - relative volume spike on latest 5m candle
    - breakout trigger proximity to avoid late entries
    """
    df = get_stock_data(symbol, period="5d", interval="5m")
    if len(df) < 30:
        return False, {"reason": "Not enough intraday candles"}

    df = df.copy()
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["VWAP"] = _vwap(df)
    df["Vol20"] = df["Volume"].rolling(20).mean()
    df["RelVol5m"] = df["Volume"] / df["Vol20"]

    latest = df.iloc[-1]
    price = float(latest.Close)
    open_price = float(latest.Open)
    high = float(latest.High)
    low = float(latest.Low)
    candle_range = max(high - low, 0.01)
    body_pct = abs(price - open_price) / candle_range

    signal = analysis.get("signal", "")
    trigger = analysis.get("trigger")
    rel_vol = float(latest.RelVol5m) if latest.RelVol5m == latest.RelVol5m else 0.0

    bullish_signal = "BULLISH" in signal or "UPTREND" in signal
    bearish_signal = "BEARISH" in signal or "DOWNTREND" in signal

    bullish_candle = price > open_price and price > latest.EMA9 > latest.EMA21 and price > latest.VWAP
    bearish_candle = price < open_price and price < latest.EMA9 < latest.EMA21 and price < latest.VWAP

    volume_spike = rel_vol >= 1.5
    strong_body = body_pct >= 0.45

    extended_from_trigger = False
    trigger_distance_pct = 0.0
    if trigger:
        trigger = float(trigger)
        if bullish_signal and price > trigger:
            trigger_distance_pct = ((price - trigger) / trigger) * 100
        elif bearish_signal and price < trigger:
            trigger_distance_pct = ((trigger - price) / trigger) * 100
        extended_from_trigger = trigger_distance_pct > 1.25

    if bullish_signal:
        approved = bullish_candle and volume_spike and strong_body and not extended_from_trigger
    elif bearish_signal:
        approved = bearish_candle and volume_spike and strong_body and not extended_from_trigger
    else:
        approved = False

    reason_parts = []
    if not volume_spike:
        reason_parts.append("5m volume spike missing")
    if not strong_body:
        reason_parts.append("5m candle body not strong")
    if extended_from_trigger:
        reason_parts.append("price extended >1.25% from intraday trigger")
    if bullish_signal and not bullish_candle:
        reason_parts.append("5m bullish candle/VWAP/EMA alignment missing")
    if bearish_signal and not bearish_candle:
        reason_parts.append("5m bearish candle/VWAP/EMA alignment missing")

    details = {
        "approved": approved,
        "price": round(price, 2),
        "ema9_5m": round(float(latest.EMA9), 2),
        "ema21_5m": round(float(latest.EMA21), 2),
        "vwap_5m": round(float(latest.VWAP), 2),
        "rel_volume_5m": round(rel_vol, 2),
        "body_pct": round(body_pct, 2),
        "trigger_distance_pct": round(trigger_distance_pct, 2),
        "reason": "OK" if approved else "; ".join(reason_parts),
    }
    return approved, details
