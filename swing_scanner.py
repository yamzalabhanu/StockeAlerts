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


<<<<<<< HEAD
=======
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


def _safe_list(values):
    return [safe_float(x) for x in (values or []) if x is not None]


>>>>>>> b32505341b9ca06d788e06a563d8d05f8284bc80
def _ema(values, length):
    if not values or len(values) < length:
        return None

    k = 2 / (length + 1)
    ema_val = sum(values[:length]) / length

    for v in values[length:]:
        ema_val = v * k + ema_val * (1 - k)

    return ema_val

<<<<<<< HEAD

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
=======
def score_swing_setup(tech: Dict):
    tech = tech or {}
    score, reasons, direction = _trend_score(tech)

    if len(values) < length + 1:
        return None

    price = safe_float(tech.get("price"))
    if not price:
        return None

    atr = safe_float(tech.get("atr14") or tech.get("atr"))
    if not atr:
        atr = max(price * 0.015, 1)

    if direction == "CALL":
        stop = round(price - (atr * SWING_ATR_STOP_MULTIPLIER), 2)
        target = round(price + (atr * SWING_ATR_TARGET_MULTIPLIER), 2)
    else:
        if weekly in bearish:
            score += 12
            reasons.append("weekly trend bearish")

        if daily in bearish:
            score += 10
            reasons.append("daily structure bearish")

        if h4 in bearish:
            score += 8
            reasons.append("4H entry trend aligned")

    return score, reasons


def _score_direction(
    direction,
    tech,
    price,
    atr,
    closes,
) -> Tuple[int, list, float, float, float]:

    ema20 = _ema(closes, 20) or tech.get("dma20")
    ema50 = _ema(closes, 50) or tech.get("dma50")
    sma200 = tech.get("dma200")

    rsi = tech.get("rsi") or _rsi(closes, 14)

    macd_val, signal, hist = _macd(closes)

    score, reasons = 0, []

    scoring_blocks = [
        _trend_strength_score(
            direction,
            tech,
            price,
            ema20,
            ema50,
            sma200,
        ),
        _rsi_score(direction, rsi),
        _volume_score(tech),
        _macd_score(direction, macd_val, signal, hist),
        _adx_proxy_score(tech, ema20, ema50),
        _structure_score(direction, tech, price, ema20, ema50),
        _relative_strength_score(direction, tech),
        _mtf_trend_score(direction, tech),
    ]

    for add_score, add_reasons in scoring_blocks:
        score += add_score
        reasons.extend(add_reasons)
>>>>>>> b32505341b9ca06d788e06a563d8d05f8284bc80

    if direction == "CALL":
        stop = price - atr * SWING_ATR_STOP_MULTIPLIER
        target = price + atr * SWING_ATR_TARGET_MULTIPLIER
    else:
        stop = price + atr * SWING_ATR_STOP_MULTIPLIER
        target = price - atr * SWING_ATR_TARGET_MULTIPLIER

    risk = abs(price - stop)
    reward = abs(target - price)
    rr = round(reward / risk, 2) if risk else 0

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
        "direction": direction,
        "score": score,
        "tier": tier,
        "entry": round(price, 2),
        "stop": stop,
        "target": target,
        "risk_reward": rr,
        "hold_days": max(SWING_HOLD_DAYS_MIN, min(SWING_HOLD_DAYS_MAX, 5)),
        "reasons": reasons,
    }


def format_swing_alert(ticker: str, setup: Dict) -> str:
    setup = setup or {}

    emoji = "🟢" if setup.get("direction") == "CALL" else "🔴"

    probability = setup.get("ml_probability")
    reasoning = setup.get("ai_reasoning") or {}
    narrative = reasoning.get("narrative", "")

    regime = (reasoning.get("regime") or {}).get("regime", "UNKNOWN")
    mtf = (reasoning.get("mtf") or {}).get("structure", "UNKNOWN")
    execution = (reasoning.get("execution") or {}).get("quality", "UNKNOWN")
    vision = (reasoning.get("vision") or {}).get("quality", "UNKNOWN")
    learning_confidence = reasoning.get("learning_confidence") or {}
    learning_stats = learning_confidence.get("learning_stats") or {}

    prob_line = f"🧠 ML Probability: {probability}\n" if probability is not None else ""
    history_line = (
        f"📚 History: WR {float(learning_stats.get('win_rate', 0)) * 100:.1f}% | "
        f"Forecast {float(learning_stats.get('forecast_accuracy', 0)) * 100:.1f}% | "
        f"Confidence {setup.get('calibrated_confidence', setup.get('score', 0))}% "
        f"({setup.get('confidence_adjustment', 0):+.1f})\n"
    )

    return (

        f'{emoji} *{setup.get("tier", "WATCH")} '
        f'SWING {setup.get("direction", "CALL")} '
        f'SETUP: {ticker}*\n'
        f'⭐ Score: {setup.get("score", 0)}/100\n'
        f'{prob_line}'
        f'{history_line}'
        f'⏳ Hold: {setup.get("hold_days", "?")} days\n'
        f'🎯 Entry: {setup.get("entry", "?")}\n'
        f'🛑 Stop: {setup.get("stop", "?")}\n'
        f'🚀 Target: {setup.get("target", "?")}\n'
        f'📐 RR: {setup.get("risk_reward", "?")}:1\n'
        f'📝 Reasons: {", ".join(setup.get("reasons", []))}\n'
        f'🧠 AI Decision: '
        f'{reasoning.get("decision", setup.get("tier", "WATCH"))}\n'
        f'📊 Composite Score: '
        f'{reasoning.get("final_score", setup.get("score", 0))}/100\n'
        f"🌍 Regime: {regime}\n"
        f"🧭 MTF: {mtf}\n"
        f"⚡ Execution: {execution}\n"
        f"🏗️ Structure: {vision}\n"
        f"\n🧠 AI Reasoning:\n{narrative}\n"
    )
