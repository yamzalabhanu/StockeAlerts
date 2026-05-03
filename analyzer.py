def analyze_stock(df):
    latest = df.iloc[-1]

    bullish = latest.Close > latest.EMA8 > latest.EMA21 > latest.EMA50
    bearish = latest.Close < latest.EMA8 < latest.EMA21 < latest.EMA50

    breakout = latest.Close > latest.High50
    breakdown = latest.Close < latest.Low50

    if bullish and breakout:
        signal = "BULLISH BREAKOUT"
    elif bearish and breakdown:
        signal = "BEARISH BREAKDOWN"
    elif bullish:
        signal = "UPTREND"
    elif bearish:
        signal = "DOWNTREND"
    else:
        signal = "SIDEWAYS"

    return {
        "signal": signal,
        "price": float(latest.Close),
        "ema8": float(latest.EMA8),
        "ema21": float(latest.EMA21),
        "ema50": float(latest.EMA50)
    }
