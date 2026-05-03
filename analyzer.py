def analyze_stock(df):
    latest = df.iloc[-1]

    bullish = latest.Close > latest.EMA8 > latest.EMA21 > latest.EMA50
    bearish = latest.Close < latest.EMA8 < latest.EMA21 < latest.EMA50

    breakout = latest.Close > latest.High20
    breakdown = latest.Close < latest.Low20

    volume_spike = latest.RelVol > 1.5
    compression = latest.ATR14 < latest.ATR10AVG

    score = 0

    if bullish:
        score += 30
    if breakout:
        score += 25
    if volume_spike:
        score += 20
    if compression:
        score += 15

    if bearish:
        score += 20
    if breakdown:
        score += 25

    if bullish and breakout:
        signal = "BULLISH BREAKOUT"
        entry = f"Buy above {round(latest.High20,2)}"
    elif bearish and breakdown:
        signal = "BEARISH BREAKDOWN"
        entry = f"Sell below {round(latest.Low20,2)}"
    elif bullish:
        signal = "UPTREND"
        entry = "Buy pullback to EMA21"
    elif bearish:
        signal = "DOWNTREND"
        entry = "Sell near EMA21 rejection"
    else:
        signal = "SIDEWAYS"
        entry = "No trade"

    return {
        "signal": signal,
        "entry": entry,
        "score": score,
        "price": float(latest.Close),
        "ema8": float(latest.EMA8),
        "ema21": float(latest.EMA21),
        "ema50": float(latest.EMA50),
        "rel_volume": float(latest.RelVol)
    }
