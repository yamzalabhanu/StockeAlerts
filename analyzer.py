def analyze_stock(df):
    """Analyze a stock for swing-trade trend, breakout, risk, and A+ quality."""
    latest = df.iloc[-1]

    bullish = latest.Close > latest.EMA8 > latest.EMA21 > latest.EMA50
    bearish = latest.Close < latest.EMA8 < latest.EMA21 < latest.EMA50

    breakout_level = latest.High20
    breakdown_level = latest.Low20

    breakout = latest.Close > breakout_level
    breakdown = latest.Close < breakdown_level

    rel_volume = float(latest.RelVol) if latest.RelVol == latest.RelVol else 0.0
    volume_spike = rel_volume >= 1.8
    compression = latest.ATR14 < latest.ATR10AVG

    atr = float(latest.ATR14) if latest.ATR14 == latest.ATR14 else 0.0
    price = float(latest.Close)

    score = 0
    reasons = []

    if bullish:
        score += 30
        reasons.append("Bullish EMA alignment: price > EMA8 > EMA21 > EMA50")
    if bearish:
        score += 30
        reasons.append("Bearish EMA alignment: price < EMA8 < EMA21 < EMA50")

    if breakout:
        score += 25
        reasons.append("Breakout above prior 20-day high")
    if breakdown:
        score += 25
        reasons.append("Breakdown below prior 20-day low")

    if volume_spike:
        score += 20
        reasons.append("Relative volume >= 1.8x")
    elif rel_volume >= 1.2:
        score += 10
        reasons.append("Relative volume >= 1.2x")

    if compression:
        score += 15
        reasons.append("ATR compression before expansion")

    if price > latest.DMA50:
        score += 5
        reasons.append("Price above 50 DMA")

    extended_pct = 0.0
    if breakout and breakout_level > 0:
        extended_pct = ((price - float(breakout_level)) / float(breakout_level)) * 100
    elif breakdown and breakdown_level > 0:
        extended_pct = ((float(breakdown_level) - price) / float(breakdown_level)) * 100

    late_entry = extended_pct > 3.0
    if late_entry:
        score -= 25
        reasons.append("Late/extended move > 3% from trigger")

    if bullish and breakout:
        signal = "BULLISH BREAKOUT"
        trigger = float(breakout_level)
        stop = max(trigger - (1.5 * atr), float(latest.EMA21)) if atr > 0 else float(latest.EMA21)
        target = trigger + (2.0 * (trigger - stop))
        entry = f"Buy above {round(trigger, 2)} or on clean retest/hold of breakout level"
    elif bearish and breakdown:
        signal = "BEARISH BREAKDOWN"
        trigger = float(breakdown_level)
        stop = min(trigger + (1.5 * atr), float(latest.EMA21)) if atr > 0 else float(latest.EMA21)
        target = trigger - (2.0 * (stop - trigger))
        entry = f"Sell/put below {round(trigger, 2)} or on failed retest of breakdown level"
    elif bullish:
        signal = "UPTREND"
        trigger = float(latest.EMA21)
        stop = float(latest.EMA50)
        target = price + (2.0 * max(price - stop, 0))
        entry = "Buy pullback/reclaim near EMA21"
    elif bearish:
        signal = "DOWNTREND"
        trigger = float(latest.EMA21)
        stop = float(latest.EMA50)
        target = price - (2.0 * max(stop - price, 0))
        entry = "Sell/put on rejection near EMA21"
    else:
        signal = "SIDEWAYS"
        trigger = None
        stop = None
        target = None
        entry = "No trade"

    a_plus = (
        score >= 85
        and not late_entry
        and volume_spike
        and (signal in {"BULLISH BREAKOUT", "BEARISH BREAKDOWN"})
    )

    return {
        "signal": signal,
        "entry": entry,
        "score": int(max(0, min(score, 100))),
        "a_plus": bool(a_plus),
        "late_entry": bool(late_entry),
        "trigger": round(trigger, 2) if trigger else None,
        "stop": round(stop, 2) if stop else None,
        "target": round(target, 2) if target else None,
        "price": round(price, 2),
        "ema8": round(float(latest.EMA8), 2),
        "ema21": round(float(latest.EMA21), 2),
        "ema50": round(float(latest.EMA50), 2),
        "dma50": round(float(latest.DMA50), 2),
        "dma200": round(float(latest.DMA200), 2) if latest.DMA200 == latest.DMA200 else None,
        "rel_volume": round(rel_volume, 2),
        "extended_pct": round(extended_pct, 2),
        "reasons": reasons,
    }
