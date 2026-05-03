from market_data import get_stock_data


def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _vwap(df):
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    return (typical * df["Volume"]).cumsum() / df["Volume"].cumsum()


def _detect_fvg(df, bullish=True):
    """Simple 3-candle fair value gap detector."""
    if len(df) < 3:
        return False, None
    c1 = df.iloc[-3]
    c3 = df.iloc[-1]
    if bullish and c3.Low > c1.High:
        return True, {"type": "bullish_fvg", "gap_low": round(float(c1.High), 2), "gap_high": round(float(c3.Low), 2)}
    if not bullish and c3.High < c1.Low:
        return True, {"type": "bearish_fvg", "gap_high": round(float(c1.Low), 2), "gap_low": round(float(c3.High), 2)}
    return False, None


def _detect_liquidity_sweep(df, bullish=True, lookback=20):
    """Detect stop-run sweep and reclaim/reject behavior."""
    if len(df) < lookback + 2:
        return False, None
    latest = df.iloc[-1]
    prior = df.iloc[-lookback-1:-1]
    prior_high = float(prior.High.max())
    prior_low = float(prior.Low.min())

    if bullish:
        swept_low = latest.Low < prior_low and latest.Close > prior_low
        if swept_low:
            return True, {"type": "bullish_liquidity_sweep", "swept_level": round(prior_low, 2)}
    else:
        swept_high = latest.High > prior_high and latest.Close < prior_high
        if swept_high:
            return True, {"type": "bearish_liquidity_sweep", "swept_level": round(prior_high, 2)}
    return False, None


def _detect_order_block(df, bullish=True, lookback=15):
    """Approximate order-block zone: last opposite candle before directional impulse."""
    recent = df.tail(lookback)
    if len(recent) < 5:
        return False, None

    impulse = recent.iloc[-1]
    avg_range = (recent.High - recent.Low).mean()
    impulse_range = impulse.High - impulse.Low
    if impulse_range < avg_range * 1.3:
        return False, None

    for _, candle in recent.iloc[:-1][::-1].iterrows():
        bearish_candle = candle.Close < candle.Open
        bullish_candle = candle.Close > candle.Open
        if bullish and bearish_candle:
            return True, {"type": "bullish_order_block", "zone_low": round(float(candle.Low), 2), "zone_high": round(float(candle.High), 2)}
        if not bullish and bullish_candle:
            return True, {"type": "bearish_order_block", "zone_low": round(float(candle.Low), 2), "zone_high": round(float(candle.High), 2)}
    return False, None


def smc_confirmation(symbol: str, analysis: dict, interval: str = "15m") -> tuple[bool, dict]:
    """Smart Money Concepts confirmation layer.

    Uses approximations of:
    - liquidity sweep
    - fair value gap
    - order block / demand-supply zone
    - VWAP/EMA directional context
    - volume imbalance
    """
    signal = analysis.get("signal", "")
    bullish = "BULLISH" in signal or "UPTREND" in signal
    bearish = "BEARISH" in signal or "DOWNTREND" in signal
    if not bullish and not bearish:
        return False, {"reason": "No directional SMC context"}

    df = get_stock_data(symbol, period="5d", interval=interval)
    if len(df) < 30:
        return False, {"reason": "Not enough candles for SMC confirmation"}

    df = df.copy()
    df["EMA9"] = _ema(df["Close"], 9)
    df["EMA21"] = _ema(df["Close"], 21)
    df["VWAP"] = _vwap(df)
    df["Vol20"] = df["Volume"].rolling(20).mean()
    df["RelVol"] = df["Volume"] / df["Vol20"]
    df = df.dropna()
    latest = df.iloc[-1]

    fvg_ok, fvg = _detect_fvg(df, bullish=bullish)
    sweep_ok, sweep = _detect_liquidity_sweep(df, bullish=bullish)
    ob_ok, order_block = _detect_order_block(df, bullish=bullish)

    if bullish:
        structure_ok = latest.Close > latest.VWAP and latest.EMA9 > latest.EMA21
    else:
        structure_ok = latest.Close < latest.VWAP and latest.EMA9 < latest.EMA21

    volume_imbalance = float(latest.RelVol) >= 1.4

    score = 0
    reasons = []
    if sweep_ok:
        score += 30
        reasons.append("liquidity sweep detected")
    if fvg_ok:
        score += 25
        reasons.append("fair value gap detected")
    if ob_ok:
        score += 20
        reasons.append("order-block zone detected")
    if structure_ok:
        score += 15
        reasons.append("VWAP/EMA structure aligned")
    if volume_imbalance:
        score += 10
        reasons.append("volume imbalance present")

    approved = score >= 55 and structure_ok

    return approved, {
        "approved": approved,
        "score": score,
        "interval": interval,
        "bias": "bullish" if bullish else "bearish",
        "price": round(float(latest.Close), 2),
        "vwap": round(float(latest.VWAP), 2),
        "ema9": round(float(latest.EMA9), 2),
        "ema21": round(float(latest.EMA21), 2),
        "rel_volume": round(float(latest.RelVol), 2),
        "liquidity_sweep": sweep,
        "fair_value_gap": fvg,
        "order_block": order_block,
        "reasons": reasons,
        "reason": "SMC confirmed" if approved else "SMC confirmation failed",
    }
