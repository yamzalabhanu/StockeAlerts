def analyze_stock(df):
    """Analyze a stock for early swing entries, breakouts, and late-entry risk."""
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    bullish = latest.Close > latest.EMA8 > latest.EMA21 > latest.EMA50
    bearish = latest.Close < latest.EMA8 < latest.EMA21 < latest.EMA50

    breakout_level = float(latest.High20)
    breakdown_level = float(latest.Low20)

    price = float(latest.Close)
    atr = float(latest.ATR14) if latest.ATR14 == latest.ATR14 else 0.0
    rel_volume = float(latest.RelVol) if latest.RelVol == latest.RelVol else 0.0

    breakout = price > breakout_level
    breakdown = price < breakdown_level

    near_breakout = breakout_level > 0 and 0 <= ((breakout_level - price) / breakout_level) * 100 <= 1.5
    near_breakdown = breakdown_level > 0 and 0 <= ((price - breakdown_level) / breakdown_level) * 100 <= 1.5

    retest_breakout = breakout_level > 0 and prev.Close > breakout_level and latest.Low <= breakout_level * 1.01 and price >= breakout_level
    retest_breakdown = breakdown_level > 0 and prev.Close < breakdown_level and latest.High >= breakdown_level * 0.99 and price <= breakdown_level

    # Relaxed thresholds so the bot produces useful B+/early alerts while still blocking late moves.
    volume_spike = rel_volume >= 1.5
    early_volume = rel_volume >= 1.2
    compression = latest.ATR14 < latest.ATR10AVG

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
    elif near_breakout:
        score += 18
        reasons.append("Early bullish setup: price within 1.5% of breakout trigger")

    if breakdown:
        score += 25
        reasons.append("Breakdown below prior 20-day low")
    elif near_breakdown:
        score += 18
        reasons.append("Early bearish setup: price within 1.5% of breakdown trigger")

    if retest_breakout:
        score += 20
        reasons.append("Breakout retest/hold detected")
    if retest_breakdown:
        score += 20
        reasons.append("Breakdown retest/rejection detected")

    if volume_spike:
        score += 20
        reasons.append("Relative volume >= 1.5x")
    elif early_volume:
        score += 10
        reasons.append("Relative volume >= 1.2x")

    if compression:
        score += 15
        reasons.append("ATR compression before expansion")

    if price > latest.DMA50:
        score += 5
        reasons.append("Price above 50 DMA")

    extended_pct = 0.0
    distance_to_trigger_pct = 0.0

    if breakout and breakout_level > 0:
        extended_pct = ((price - breakout_level) / breakout_level) * 100
    elif breakdown and breakdown_level > 0:
        extended_pct = ((breakdown_level - price) / breakdown_level) * 100
    elif near_breakout and breakout_level > 0:
        distance_to_trigger_pct = ((breakout_level - price) / breakout_level) * 100
    elif near_breakdown and breakdown_level > 0:
        distance_to_trigger_pct = ((price - breakdown_level) / breakdown_level) * 100

    late_entry = extended_pct > 2.0
    very_late_entry = extended_pct > 3.0
    if late_entry:
        score -= 35
        reasons.append("Late/extended move > 2% from trigger; avoid chasing")
    if very_late_entry:
        score -= 20
        reasons.append("Very late move > 3% from trigger; reject unless retest forms")

    if bullish and retest_breakout:
        signal = "BULLISH RETEST"
        trigger = breakout_level
        stop = max(trigger - (1.25 * atr), float(latest.EMA21)) if atr > 0 else float(latest.EMA21)
        target = trigger + (2.0 * (trigger - stop))
        entry = f"Buy retest/hold near {round(trigger, 2)}; avoid if price extends >2% above trigger"
    elif bearish and retest_breakdown:
        signal = "BEARISH RETEST"
        trigger = breakdown_level
        stop = min(trigger + (1.25 * atr), float(latest.EMA21)) if atr > 0 else float(latest.EMA21)
        target = trigger - (2.0 * (stop - trigger))
        entry = f"Buy puts on failed retest near {round(trigger, 2)}; avoid if price extends >2% below trigger"
    elif bullish and breakout:
        signal = "BULLISH BREAKOUT"
        trigger = breakout_level
        stop = max(trigger - (1.5 * atr), float(latest.EMA21)) if atr > 0 else float(latest.EMA21)
        target = trigger + (2.0 * (trigger - stop))
        entry = f"Buy only near {round(trigger, 2)} or wait for retest; do not chase >2% extension"
    elif bearish and breakdown:
        signal = "BEARISH BREAKDOWN"
        trigger = breakdown_level
        stop = min(trigger + (1.5 * atr), float(latest.EMA21)) if atr > 0 else float(latest.EMA21)
        target = trigger - (2.0 * (stop - trigger))
        entry = f"Buy puts only near {round(trigger, 2)} or wait for retest; do not chase >2% extension"
    elif bullish and near_breakout:
        signal = "BULLISH EARLY WATCH"
        trigger = breakout_level
        stop = float(latest.EMA21)
        target = trigger + (2.0 * max(trigger - stop, 0))
        entry = f"Early entry only on break above {round(trigger, 2)} with volume; or starter near support with stop below EMA21"
    elif bearish and near_breakdown:
        signal = "BEARISH EARLY WATCH"
        trigger = breakdown_level
        stop = float(latest.EMA21)
        target = trigger - (2.0 * max(stop - trigger, 0))
        entry = f"Early put entry only on break below {round(trigger, 2)} with volume; or failed bounce under EMA21"
    elif bullish:
        signal = "UPTREND"
        trigger = float(latest.EMA21)
        stop = float(latest.EMA50)
        target = price + (2.0 * max(price - stop, 0))
        entry = "Buy pullback/reclaim near EMA21; avoid chasing far above trigger"
    elif bearish:
        signal = "DOWNTREND"
        trigger = float(latest.EMA21)
        stop = float(latest.EMA50)
        target = price - (2.0 * max(stop - price, 0))
        entry = "Buy puts on rejection near EMA21; avoid chasing after breakdown"
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
        and signal in {"BULLISH BREAKOUT", "BEARISH BREAKDOWN", "BULLISH RETEST", "BEARISH RETEST"}
    )

    early_a_plus = (
        score >= 65
        and not late_entry
        and early_volume
        and signal in {"BULLISH EARLY WATCH", "BEARISH EARLY WATCH"}
    )

    b_plus = (
        score >= 65
        and not late_entry
        and signal not in {"SIDEWAYS"}
    )

    return {
        "signal": signal,
        "entry": entry,
        "score": int(max(0, min(score, 100))),
        "a_plus": bool(a_plus),
        "early_a_plus": bool(early_a_plus),
        "b_plus": bool(b_plus),
        "tier": "A+" if a_plus else "Early A+" if early_a_plus else "B+" if b_plus else "C",
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
        "distance_to_trigger_pct": round(distance_to_trigger_pct, 2),
        "reasons": reasons,
    }
