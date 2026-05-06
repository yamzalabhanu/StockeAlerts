import datetime as dt
from typing import Dict, Optional

from bot_utils import safe_float
from config import (
    SWING_ATR_STOP_MULTIPLIER,
    SWING_ATR_TARGET_MULTIPLIER,
    SWING_HOLD_DAYS_MAX,
    SWING_HOLD_DAYS_MIN,
    SWING_MIN_SCORE,
    SWING_PULLBACK_TOLERANCE_PCT,
)


def _pct_diff(a, b):
    try:
        if a is None or b in (None, 0):
            return None
        return ((float(a) - float(b)) / float(b)) * 100.0
    except Exception:
        return None


def _near(price, level, tolerance_pct):
    diff = _pct_diff(price, level)
    return diff is not None and abs(diff) <= tolerance_pct


def score_swing_setup(tech: Dict) -> Optional[Dict]:
    """Score daily/4H style swing setups using available daily-derived context.

    Designed for 2-10 day holds. Uses daily moving averages, 20-day highs/lows,
    ATR-based risk, and volume participation.
    """
    if not tech:
        return None

    price = safe_float(tech.get("price"))
    atr = safe_float(tech.get("atr14"))
    dma20 = tech.get("dma20")
    dma50 = tech.get("dma50")
    dma200 = tech.get("dma200")
    recent_high = tech.get("recent_high")
    recent_low = tech.get("recent_low")
    avg_vol = safe_float(tech.get("avg_20_volume"))
    cur_vol = safe_float(tech.get("current_volume"))

    if not price or not atr:
        return None

    call_score = 0
    call_reasons = []
    put_score = 0
    put_reasons = []

    # Bullish swing criteria
    if dma20 and price > dma20:
        call_score += 15
        call_reasons.append("price above 20 DMA")
    if dma50 and price > dma50:
        call_score += 20
        call_reasons.append("price above 50 DMA")
    if dma200 and price > dma200:
        call_score += 10
        call_reasons.append("price above 200 DMA")
    if dma20 and dma50 and dma20 > dma50:
        call_score += 15
        call_reasons.append("20 DMA above 50 DMA")
    if recent_high and price >= recent_high * 0.995:
        call_score += 25
        call_reasons.append("near/above recent 20-bar high")
    if dma20 and _near(price, dma20, SWING_PULLBACK_TOLERANCE_PCT):
        call_score += 20
        call_reasons.append("pullback near 20 DMA")
    if avg_vol and cur_vol and cur_vol >= avg_vol:
        call_score += 10
        call_reasons.append("volume at/above 20-bar average")

    # Bearish swing criteria
    if dma20 and price < dma20:
        put_score += 15
        put_reasons.append("price below 20 DMA")
    if dma50 and price < dma50:
        put_score += 20
        put_reasons.append("price below 50 DMA")
    if dma200 and price < dma200:
        put_score += 10
        put_reasons.append("price below 200 DMA")
    if dma20 and dma50 and dma20 < dma50:
        put_score += 15
        put_reasons.append("20 DMA below 50 DMA")
    if recent_low and price <= recent_low * 1.005:
        put_score += 25
        put_reasons.append("near/below recent 20-bar low")
    if dma20 and _near(price, dma20, SWING_PULLBACK_TOLERANCE_PCT):
        put_score += 20
        put_reasons.append("bearish pullback/rejection near 20 DMA")
    if avg_vol and cur_vol and cur_vol >= avg_vol:
        put_score += 10
        put_reasons.append("volume at/above 20-bar average")

    if call_score >= put_score:
        direction = "CALL"
        score = call_score
        reasons = call_reasons
        stop = price - atr * SWING_ATR_STOP_MULTIPLIER
        target = price + atr * SWING_ATR_TARGET_MULTIPLIER
    else:
        direction = "PUT"
        score = put_score
        reasons = put_reasons
        stop = price + atr * SWING_ATR_STOP_MULTIPLIER
        target = price - atr * SWING_ATR_TARGET_MULTIPLIER

    risk = abs(price - stop)
    reward = abs(target - price)
    rr = reward / risk if risk else 0

    if score < SWING_MIN_SCORE:
        return None

    return {
        "alert_type": "SWING",
        "direction": direction,
        "score": score,
        "entry": round(price, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "risk_reward": round(rr, 2),
        "hold_days": f"{SWING_HOLD_DAYS_MIN}-{SWING_HOLD_DAYS_MAX}",
        "timeframe": "Daily / multi-day",
        "reasons": reasons,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def format_swing_alert(ticker: str, setup: Dict) -> str:
    emoji = "🟢" if setup.get("direction") == "CALL" else "🔴"
    return (
        f"{emoji} *SWING {setup['direction']} SETUP: {ticker}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⏳ *Hold:* {setup['hold_days']} days\n"
        f"📅 *Timeframe:* {setup['timeframe']}\n"
        f"⭐ *Score:* {setup['score']}/100\n"
        f"🎯 *Entry:* {setup['entry']}\n"
        f"🛑 *Stop:* {setup['stop']}\n"
        f"🚀 *Target:* {setup['target']}\n"
        f"📐 *R/R:* {setup['risk_reward']}:1\n"
        f"📝 *Reasons:* {', '.join(setup.get('reasons', []))}"
    )
