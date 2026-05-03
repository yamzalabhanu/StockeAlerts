from market_data import get_stock_data


def _vwap(df):
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    return (typical * df["Volume"]).cumsum() / df["Volume"].cumsum()


def intraday_confirmation(symbol: str, analysis: dict) -> tuple[bool, dict]:
    """Confirm setup with relaxed recent 5-minute price action.

    Works with both:
    - main.py/analyzer payloads: signal, score, trigger
    - bot.py setup payloads: direction, score, trigger/recent level fields

    Relaxed logic:
    - Score >= 75: require 2 of 4 confirmations.
    - Score < 75: require 3 of 4 confirmations.
    - Allows continuation entries up to 2% from trigger.
    """
    df = get_stock_data(symbol, period="5d", interval="5m")
    if len(df) < 30:
        return False, {"approved": False, "reason": "Not enough intraday candles"}

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

    signal = str(analysis.get("signal", "") or "").upper()
    direction = str(analysis.get("direction", "") or "").upper()
    daily_score = int(analysis.get("score", 0) or 0)

    trigger = (
        analysis.get("trigger")
        or analysis.get("breakout_level")
        or analysis.get("breakdown_level")
        or analysis.get("entry")
    )

    rel_vol = float(latest.RelVol5m) if latest.RelVol5m == latest.RelVol5m else 0.0

    bullish_signal = (
        "BULLISH" in signal
        or "UPTREND" in signal
        or direction in {"CALL", "CALLS", "LONG", "BULLISH"}
    )
    bearish_signal = (
        "BEARISH" in signal
        or "DOWNTREND" in signal
        or direction in {"PUT", "PUTS", "SHORT", "BEARISH"}
    )

    ema9 = float(latest.EMA9)
    ema21 = float(latest.EMA21)
    vwap = float(latest.VWAP)

    if bullish_signal:
        ema_align = price >= ema9 * 0.997 and ema9 >= ema21 * 0.997
        vwap_ok = price > vwap
        candle_ok = price > open_price and body_pct >= 0.30
    elif bearish_signal:
        ema_align = price <= ema9 * 1.003 and ema9 <= ema21 * 1.003
        vwap_ok = price < vwap
        candle_ok = price < open_price and body_pct >= 0.30
    else:
        ema_align = False
        vwap_ok = False
        candle_ok = False

    volume_ok = rel_vol >= 1.5

    trigger_distance_pct = 0.0
    if trigger:
        try:
            trigger = float(trigger)
            if bullish_signal and price > trigger:
                trigger_distance_pct = ((price - trigger) / trigger) * 100
            elif bearish_signal and price < trigger:
                trigger_distance_pct = ((trigger - price) / trigger) * 100
        except (TypeError, ValueError):
            trigger_distance_pct = 0.0

    not_too_extended = trigger_distance_pct <= 2.0

    confirmations = sum([
        bool(ema_align),
        bool(vwap_ok),
        bool(candle_ok),
        bool(volume_ok),
    ])

    required_confirmations = 2 if daily_score >= 75 else 3
    approved = confirmations >= required_confirmations and not_too_extended

    reason_parts = []
    if not ema_align:
        reason_parts.append("5m EMA alignment missing")
    if not vwap_ok:
        reason_parts.append("5m VWAP alignment missing")
    if not candle_ok:
        reason_parts.append("5m candle confirmation missing or body <0.30")
    if not volume_ok:
        reason_parts.append("5m volume spike missing")
    if not not_too_extended:
        reason_parts.append("price extended >2.0% from intraday trigger")

    approval_reason = (
        f"Approved: relaxed {confirmations}/{required_confirmations} intraday confirmation"
        if approved
        else "; ".join(reason_parts)
    )

    details = {
        "approved": bool(approved),
        "confirmations": int(confirmations),
        "required_confirmations": int(required_confirmations),
        "price": round(price, 2),
        "ema9_5m": round(ema9, 2),
        "ema21_5m": round(ema21, 2),
        "vwap_5m": round(vwap, 2),
        "rel_volume_5m": round(rel_vol, 2),
        "body_pct": round(body_pct, 2),
        "trigger_distance_pct": round(trigger_distance_pct, 2),
        "ema_align": bool(ema_align),
        "vwap_ok": bool(vwap_ok),
        "candle_ok": bool(candle_ok),
        "volume_ok": bool(volume_ok),
        "reason": approval_reason,
    }
    return bool(approved), details
