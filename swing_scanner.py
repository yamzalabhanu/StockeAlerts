import datetime as dt
from typing import Dict, Tuple

from bot_utils import safe_float
from config import (
    MIN_RISK_REWARD,
    SWING_A_PLUS_SCORE,
    SWING_A_SCORE,
    SWING_ATR_STOP_MULTIPLIER,
    SWING_ATR_TARGET_MULTIPLIER,
    SWING_HOLD_DAYS_MAX,
    SWING_HOLD_DAYS_MIN,
)


def _ema(values, length):
    if not values or len(values) < length:
        return None

    k = 2 / (length + 1)
    ema_val = sum(values[:length]) / length

    for v in values[length:]:
        ema_val = v * k + ema_val * (1 - k)

    return ema_val


def _rsi(values, length=14):
    if not values or len(values) < length + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))

    avg_gain = sum(gains[-length:]) / length
    avg_loss = sum(losses[-length:]) / length

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _trend_score(tech: Dict):
    score = 0
    reasons = []

    price = safe_float((tech or {}).get("price"))
    ema20 = safe_float((tech or {}).get("ema20") or (tech or {}).get("dma20"))
    ema50 = safe_float((tech or {}).get("ema50") or (tech or {}).get("dma50"))
    ema200 = safe_float((tech or {}).get("ema200") or (tech or {}).get("dma200"))
    rsi = safe_float((tech or {}).get("rsi"))
    adx = safe_float((tech or {}).get("adx"))
    rel_volume = safe_float((tech or {}).get("rel_volume"))

    bullish = (
        price > ema20 > ema50 > ema200
        if all([price, ema20, ema50, ema200])
        else False
    )

    bearish = (
        price < ema20 < ema50 < ema200
        if all([price, ema20, ema50, ema200])
        else False
    )

    if bullish:
        score += 35
        reasons.append("Bullish EMA alignment")

    if bearish:
        score += 35
        reasons.append("Bearish EMA alignment")

    if 55 <= rsi <= 75:
        score += 15
        reasons.append(f"RSI healthy {rsi:.1f}")

    if adx >= 20:
        score += 15
        reasons.append(f"Strong ADX {adx:.1f}")

    if rel_volume >= 1.5:
        score += 15
        reasons.append(f"Strong RVOL {rel_volume:.1f}x")

    direction = "CALL" if bullish else "PUT" if bearish else None

    return score, reasons, direction


def score_swing_setup(tech: Dict):
    tech = tech or {}

    score, reasons, direction = _trend_score(tech)

    if not direction:
        return None

    atr = safe_float(tech.get("atr14") or tech.get("atr"))
    price = safe_float(tech.get("price"))

    if not price:
        return None

    if not atr:
        atr = max(price * 0.015, 1)

    if direction == "CALL":
        stop = price - atr * SWING_ATR_STOP_MULTIPLIER
        target = price + atr * SWING_ATR_TARGET_MULTIPLIER
    else:
        stop = price + atr * SWING_ATR_STOP_MULTIPLIER
        target = price - atr * SWING_ATR_TARGET_MULTIPLIER

    risk = abs(price - stop)
    reward = abs(target - price)

    rr = reward / risk if risk else 0

    if rr < max(MIN_RISK_REWARD - 0.5, 1.2):
        return None

    if len(reasons) < 2:
        return None

    if score < 45:
        return None

    tier = "A+"

    if score < SWING_A_PLUS_SCORE:
        tier = "A"

    if score < SWING_A_SCORE:
        tier = "WATCH"

    return {
        "alert_type": "SWING",
        "tier": tier,
        "direction": direction,
        "score": min(score, 100),
        "entry": round(price, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "risk_reward": round(rr, 2),
        "hold_days": f"{SWING_HOLD_DAYS_MIN}-{SWING_HOLD_DAYS_MAX}",
        "timeframe": "Weekly / Daily / 4H",
        "reasons": reasons[:10],
        "created_at": dt.datetime.now(
            dt.timezone.utc
        ).isoformat(),
    }


def format_swing_alert(ticker: str, setup: Dict) -> str:
    setup = setup or {}

    emoji = "🟢" if setup.get("direction") == "CALL" else "🔴"

    probability = setup.get("ml_probability")

    reasoning = setup.get("ai_reasoning") or {}

    narrative = reasoning.get("narrative", "")

    regime = (
        reasoning.get("regime") or {}
    ).get("regime", "UNKNOWN")

    mtf = (
        reasoning.get("mtf") or {}
    ).get("structure", "UNKNOWN")

    execution = (
        reasoning.get("execution") or {}
    ).get("quality", "UNKNOWN")

    vision = (
        reasoning.get("vision") or {}
    ).get("quality", "UNKNOWN")

    prob_line = (
        f"🧠 ML Probability: {probability}\n"
        if probability is not None
        else ""
    )

    return (
        f"{emoji} *{setup.get('tier', 'WATCH')} "
        f"SWING {setup.get('direction', 'CALL')} "
        f"SETUP: {ticker}*\n"
        f"⭐ Score: {setup.get('score', 0)}/100\n"
        f"{prob_line}"
        f"⏳ Hold: {setup.get('hold_days', '?')} days\n"
        f"🎯 Entry: {setup.get('entry', '?')}\n"
        f"🛑 Stop: {setup.get('stop', '?')}\n"
        f"🚀 Target: {setup.get('target', '?')}\n"
        f"📐 RR: {setup.get('risk_reward', '?')}:1\n"
        f"📝 Reasons: {', '.join(setup.get('reasons', []))}\n"
        f"🧠 AI Decision: "
        f"{reasoning.get('decision', setup.get('tier', 'WATCH'))}\n"
        f"📊 Composite Score: "
        f"{reasoning.get('final_score', setup.get('score', 0))}/100\n"
        f"🌍 Regime: {regime}\n"
        f"🧭 MTF: {mtf}\n"
        f"⚡ Execution: {execution}\n"
        f"🏗️ Structure: {vision}\n"
        f"\n🧠 AI Reasoning:\n{narrative}\n"
    )
