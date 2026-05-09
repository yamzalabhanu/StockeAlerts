from __future__ import annotations

import datetime as dt
from typing import Dict, Optional, Tuple

from alert_formatting import format_predicted_price_move, format_recommended_option_contract

import config
from bot_utils import safe_float
from performance_learning import default_learning_stats
from config import (
    MIN_RISK_REWARD,
    SWING_A_PLUS_SCORE,
    SWING_A_SCORE,
    SWING_ATR_STOP_MULTIPLIER,
    SWING_ATR_TARGET_MULTIPLIER,
    SWING_HOLD_DAYS_MAX,
    SWING_HOLD_DAYS_MIN,
    SWING_MIN_REASONS,
    SWING_MIN_SCORE,
)

DEFAULT_SWING_PULLBACK_TOLERANCE_PCT = 1.0
SWING_PULLBACK_TOLERANCE_PCT = (
    safe_float(
        getattr(
            config,
            "SWING_PULLBACK_TOLERANCE_PCT",
            DEFAULT_SWING_PULLBACK_TOLERANCE_PCT,
        )
    )
    or DEFAULT_SWING_PULLBACK_TOLERANCE_PCT
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


def _safe_list(values):
    return [safe_float(x) for x in (values or []) if x is not None]


def _ema(values, length):
    values = _safe_list(values)

    if len(values) < length:
        return None

    k = 2 / (length + 1)

    ema_val = sum(values[:length]) / length

    for price in values[length:]:
        ema_val = price * k + ema_val * (1 - k)

    return ema_val


def _rsi(values, length=14):
    values = _safe_list(values)

    if len(values) < length + 1:
        return None

    gains, losses = [], []

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


def _macd(values):
    values = _safe_list(values)

    if len(values) < 35:
        return None, None, None

    ema12_series = []
    ema26_series = []

    for i in range(len(values)):
        ema12_series.append(_ema(values[: i + 1], 12))
        ema26_series.append(_ema(values[: i + 1], 26))

    macd_series = [
        a - b
        for a, b in zip(ema12_series, ema26_series)
        if a is not None and b is not None
    ]

    if len(macd_series) < 9:
        return None, None, None

    signal = _ema(macd_series, 9)
    macd_val = macd_series[-1]
    hist = macd_val - signal if signal is not None else None

    return macd_val, signal, hist


def _trend_strength_score(direction, tech, price, ema20, ema50, sma200):
    score, reasons = 0, []

    if direction == "CALL":
        if ema20 and price > ema20:
            score += 10
            reasons.append("price above 20 EMA")

        if ema50 and price > ema50:
            score += 10
            reasons.append("price above 50 EMA")

        if sma200 and price > sma200:
            score += 10
            reasons.append("price above 200 SMA")

        if ema20 and ema50 and ema20 > ema50:
            score += 10
            reasons.append("20 EMA above 50 EMA")

        if ema50 and sma200 and ema50 > sma200:
            score += 10
            reasons.append("50 EMA above 200 SMA")

    else:
        if ema20 and price < ema20:
            score += 10
            reasons.append("price below 20 EMA")

        if ema50 and price < ema50:
            score += 10
            reasons.append("price below 50 EMA")

        if sma200 and price < sma200:
            score += 10
            reasons.append("price below 200 SMA")

        if ema20 and ema50 and ema20 < ema50:
            score += 10
            reasons.append("20 EMA below 50 EMA")

        if ema50 and sma200 and ema50 < sma200:
            score += 10
            reasons.append("50 EMA below 200 SMA")

    return score, reasons


def _rsi_score(direction, rsi):
    if rsi is None:
        return 0, []

    score, reasons = 0, []

    if direction == "CALL":
        if 55 <= rsi <= 70:
            score += 15
            reasons.append(f"RSI ideal bullish zone {rsi:.1f}")

        elif 40 <= rsi < 55:
            score += 8
            reasons.append(f"RSI bounce zone {rsi:.1f}")

        elif rsi > 80:
            score -= 10
            reasons.append(f"RSI overextended {rsi:.1f}")

        elif rsi < 40:
            score -= 8
            reasons.append(f"RSI weak {rsi:.1f}")

    else:
        if 30 <= rsi <= 45:
            score += 15
            reasons.append(f"RSI bearish momentum zone {rsi:.1f}")

        elif 45 < rsi <= 60:
            score += 8
            reasons.append(f"RSI rejection zone {rsi:.1f}")

        elif rsi > 65:
            score -= 8
            reasons.append(f"RSI too strong for puts {rsi:.1f}")

    return score, reasons


def _volume_score(tech):
    avg_vol = safe_float(tech.get("avg_20_volume"))
    cur_vol = safe_float(tech.get("current_volume"))
    rel_vol = safe_float(tech.get("rel_volume"))

    if not rel_vol and avg_vol and cur_vol:
        rel_vol = cur_vol / avg_vol

    score, reasons = 0, []

    if not rel_vol:
        return 0, []

    if rel_vol >= 3:
        score += 20
        reasons.append(f"institutional volume {rel_vol:.1f}x")

    elif rel_vol >= 2:
        score += 15
        reasons.append(f"strong volume {rel_vol:.1f}x")

    elif rel_vol >= 1.5:
        score += 10
        reasons.append(f"volume confirmation {rel_vol:.1f}x")

    elif rel_vol < 0.7:
        score -= 8
        reasons.append(f"weak volume {rel_vol:.1f}x")

    return score, reasons


def _macd_score(direction, macd_val, signal, hist):
    if macd_val is None or signal is None or hist is None:
        return 0, []

    score, reasons = 0, []

    if direction == "CALL":
        if macd_val > signal:
            score += 10
            reasons.append("MACD bullish cross")

        if hist > 0:
            score += 5
            reasons.append("MACD histogram positive")

        if macd_val > 0:
            score += 5
            reasons.append("MACD above zero")

    else:
        if macd_val < signal:
            score += 10
            reasons.append("MACD bearish cross")

        if hist < 0:
            score += 5
            reasons.append("MACD histogram negative")

        if macd_val < 0:
            score += 5
            reasons.append("MACD below zero")

    return score, reasons


def _adx_proxy_score(tech, ema20, ema50):
    adx = tech.get("adx")

    score, reasons = 0, []

    if adx is not None:
        adx = safe_float(adx)

        if adx >= 25:
            score += 10
            reasons.append(f"ADX strong trend {adx:.1f}")

        elif adx >= 20:
            score += 6
            reasons.append(f"ADX trend forming {adx:.1f}")

        elif adx < 18:
            score -= 10
            reasons.append(f"ADX chop risk {adx:.1f}")

        return score, reasons

    if ema20 and ema50:
        spread = abs(_pct_diff(ema20, ema50) or 0)

        if spread >= 1.5:
            score += 6
            reasons.append(f"EMA spread trend proxy {spread:.1f}%")

        elif spread < 0.4:
            score -= 5
            reasons.append("EMA spread too tight / chop risk")

    return score, reasons


def _structure_score(direction, tech, price, ema20, ema50):
    score, reasons = 0, []

    recent_high = tech.get("recent_high")
    recent_low = tech.get("recent_low")
    prev_high = tech.get("prev_high")
    prev_low = tech.get("prev_low")

    last_lows = _safe_list(tech.get("last_5_lows"))
    last_highs = _safe_list(tech.get("last_5_highs"))

    if direction == "CALL":
        resistance = max(
            [x for x in [recent_high, prev_high] if x] or [0]
        )

        if resistance and price >= resistance * 0.995:
            score += 15
            reasons.append("breakout near/above resistance")

        if ema20 and _near(price, ema20, SWING_PULLBACK_TOLERANCE_PCT):
            score += 12
            reasons.append("EMA20 pullback zone")

        if ema50 and _near(price, ema50, SWING_PULLBACK_TOLERANCE_PCT):
            score += 8
            reasons.append("EMA50 swing support zone")

    else:
        support = min(
            [x for x in [recent_low, prev_low] if x] or [0]
        )

        if support and price <= support * 1.005:
            score += 15
            reasons.append("breakdown near/below support")

        if ema20 and _near(price, ema20, SWING_PULLBACK_TOLERANCE_PCT):
            score += 12
            reasons.append("EMA20 rejection zone")

        if ema50 and _near(price, ema50, SWING_PULLBACK_TOLERANCE_PCT):
            score += 8
            reasons.append("EMA50 swing rejection zone")

    return score, reasons


def _relative_strength_score(direction, tech):
    rs = str(
        tech.get("relative_strength", tech.get("rs_vs_spy", ""))
    ).upper()

    if direction == "CALL" and rs in {
        "STRONG",
        "BULLISH",
        "OUTPERFORM",
    }:
        return 10, ["relative strength vs market"]

    if direction == "PUT" and rs in {
        "WEAK",
        "BEARISH",
        "UNDERPERFORM",
    }:
        return 10, ["relative weakness vs market"]

    return 0, []


def _mtf_trend_score(direction, tech):
    score, reasons = 0, []

    weekly = str(tech.get("weekly_trend", "")).upper()
    daily = str(tech.get("daily_trend", "")).upper()
    h4 = str(tech.get("h4_trend", tech.get("trend_4h", ""))).upper()

    bullish = {"BULLISH", "UP", "UPTREND"}
    bearish = {"BEARISH", "DOWN", "DOWNTREND"}

    if direction == "CALL":
        if weekly in bullish:
            score += 12
            reasons.append("weekly trend bullish")

        if daily in bullish:
            score += 10
            reasons.append("daily structure bullish")

        if h4 in bullish:
            score += 8
            reasons.append("4H entry trend aligned")

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

    if direction == "CALL":
        stop = price - atr * SWING_ATR_STOP_MULTIPLIER
        target = price + atr * SWING_ATR_TARGET_MULTIPLIER

    else:
        stop = price + atr * SWING_ATR_STOP_MULTIPLIER
        target = price - atr * SWING_ATR_TARGET_MULTIPLIER

    risk = abs(price - stop)
    reward = abs(target - price)

    rr = reward / risk if risk else 0

    if rr < MIN_RISK_REWARD:
        score -= 10
        reasons.append(f"RR below minimum {rr:.2f}")

    return int(max(score, 0)), reasons, stop, target, rr


def _tier(score, reasons_count):
    if score >= SWING_A_PLUS_SCORE and reasons_count >= 5:
        return "A+"

    if score >= SWING_A_SCORE and reasons_count >= 4:
        return "A"

    return "WATCH"


def score_swing_setup(tech: Dict) -> Optional[Dict]:
    tech = tech or {}

    price = safe_float(tech.get("price"))
    atr = safe_float(tech.get("atr14"))

    if not price:
        return None

    if not atr:
        atr = max(price * 0.02, 1.0)

    closes = (
        tech.get("daily_closes")
        or tech.get("last_60_closes")
        or tech.get("last_5_closes")
    )

    closes = _safe_list(closes) or [price]

    (
        call_score,
        call_reasons,
        call_stop,
        call_target,
        call_rr,
    ) = _score_direction(
        "CALL",
        tech,
        price,
        atr,
        closes,
    )

    (
        put_score,
        put_reasons,
        put_stop,
        put_target,
        put_rr,
    ) = _score_direction(
        "PUT",
        tech,
        price,
        atr,
        closes,
    )

    if call_score >= put_score:
        direction = "CALL"
        score = call_score
        reasons = call_reasons
        stop = call_stop
        target = call_target
        rr = call_rr

    else:
        direction = "PUT"
        score = put_score
        reasons = put_reasons
        stop = put_stop
        target = put_target
        rr = put_rr

    if score < SWING_MIN_SCORE:
        return None

    if len(reasons) < SWING_MIN_REASONS:
        return None

    tier = _tier(score, len(reasons))

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

    emoji = (
        "🟢"
        if setup.get("direction") == "CALL"
        else "🔴"
    )

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

    learning_confidence = reasoning.get("learning_confidence") or {}
    learning_stats = default_learning_stats()
    learning_stats.update(learning_confidence.get("learning_stats") or {})

    prob_line = (
        f"🧠 ML Probability: {probability}\n"
        if probability is not None
        else ""
    )
    history_line = (
        f"📚 History: WR {float(learning_stats.get('win_rate', 0)) * 100:.1f}% | "
        f"Forecast {float(learning_stats.get('forecast_accuracy', 0)) * 100:.1f}% | "
        f"Confidence {setup.get('calibrated_confidence', setup.get('score', 0))}% "
        f"({setup.get('confidence_adjustment', 0):+.1f})\n"
    )

    options_flow = setup.get("options_flow") or {}
    option_contract = setup.get("option_contract") or {}
    options_flow_line = ""
    if options_flow:
        flow_signals = options_flow.get("signals") or []
        top_signals = ", ".join(str(s.get("name")) for s in flow_signals[:3] if isinstance(s, dict)) or "none"
        options_flow_line = (
            f"🧨 Options Flow: {options_flow.get('bias')} {options_flow.get('score')}/100 | "
            f"Gamma {options_flow.get('dealer_gamma_state')} | Squeeze {options_flow.get('gamma_squeeze')} | "
            f"Signals {top_signals}\n"
        )

    predicted_move_line = format_predicted_price_move(
        setup.get("direction"),
        setup.get("entry"),
        setup.get("target"),
        setup.get("stop"),
    )
    option_contract_line = ""
    if option_contract:
        option_contract_line = format_recommended_option_contract(
            option_contract,
            direction=setup.get("direction", ""),
            entry=setup.get("entry"),
            target=setup.get("target"),
        ).lstrip("\n")

    return (
        f'{emoji} *{setup.get("tier", "WATCH")} '
        f'SWING {setup.get("direction", "CALL")} '
        f'SETUP: {ticker}*\n'
        f'⭐ Score: {setup.get("score", 0)}/100\n'
        f"{prob_line}"
        f"{history_line}"
        f'⏳ Hold: {setup.get("hold_days", "?")} days\n'
        f'🎯 Entry: {setup.get("entry", "?")}\n'
        f'🛑 Stop: {setup.get("stop", "?")}\n'
        f'🚀 Target: {setup.get("target", "?")}\n'
        f"{predicted_move_line}"
        f'📐 RR: {setup.get("risk_reward", "?")}:1\n'
        f"{options_flow_line}"
        f"{option_contract_line}"
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
