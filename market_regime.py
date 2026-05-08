from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from bot_utils import safe_float


@dataclass
class RegimeAdjustment:
    regime: str
    score_adjustment: int
    min_score_adjustment: int
    reason: str


TRENDING_BULL = "TRENDING_BULL"
TRENDING_BEAR = "TRENDING_BEAR"
CHOPPY = "CHOPPY"
HIGH_VOL = "HIGH_VOL"
LOW_VOL = "LOW_VOL"
MIXED = "MIXED"


def detect_market_regime(market: Dict, market_stats: Dict | None = None) -> Dict:
    bullish = int(market.get("bullish_count", 0) or 0)
    bearish = int(market.get("bearish_count", 0) or 0)
    bias = market.get("bias", "NEUTRAL")

    vix = safe_float((market_stats or {}).get("vix"))
    adx = safe_float((market_stats or {}).get("adx"))
    atr_expansion = safe_float((market_stats or {}).get("atr_expansion"))

    reasons = []
    confidence = 50

    if bullish >= 3 and bias == "BULLISH":
        regime = TRENDING_BULL
        confidence = 85
        reasons.append("ETF breadth bullish")

    elif bearish >= 3 and bias == "BEARISH":
        regime = TRENDING_BEAR
        confidence = 85
        reasons.append("ETF breadth bearish")

    elif abs(bullish - bearish) <= 1:
        regime = CHOPPY
        confidence = 75
        reasons.append("Mixed ETF breadth")

    else:
        regime = MIXED
        confidence = 60
        reasons.append("Partial market alignment")

    if adx:
        if adx > 25:
            confidence += 5
            reasons.append(f"Strong ADX trend {adx}")
        elif adx < 18:
            regime = CHOPPY
            confidence = max(confidence, 80)
            reasons.append(f"Low ADX chop risk {adx}")

    if vix:
        if vix > 25:
            regime = HIGH_VOL
            confidence = max(confidence, 85)
            reasons.append(f"High VIX {vix}")
        elif vix < 15:
            reasons.append(f"Low VIX {vix}")

    if atr_expansion:
        if atr_expansion < 0.7:
            regime = LOW_VOL
            confidence = max(confidence, 70)
            reasons.append("Low ATR expansion")
        elif atr_expansion > 1.5:
            reasons.append("High ATR expansion")

    return {
        "regime": regime,
        "confidence": min(confidence, 100),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "reasons": reasons,
    }


def classify_market_regime(market: Dict) -> str:
    return detect_market_regime(market).get("regime", MIXED)


def regime_adjustment(entry_mode: str, market: Dict) -> RegimeAdjustment:
    regime = classify_market_regime(market)
    entry_mode = (entry_mode or "STANDARD").upper()

    if regime in {TRENDING_BULL, TRENDING_BEAR}:
        if entry_mode in {"BREAKOUT", "MOMENTUM"}:
            return RegimeAdjustment(regime, 12, -5, "Trend regime favors momentum")
        if entry_mode == "RETEST":
            return RegimeAdjustment(regime, 8, -3, "Trend regime favors retests")
        return RegimeAdjustment(regime, 5, 0, "Trend regime setup boost")

    if regime == CHOPPY:
        if entry_mode in {"BREAKOUT", "MOMENTUM"}:
            return RegimeAdjustment(regime, -15, 8, "Choppy market penalizes chasing")
        if entry_mode in {"RETEST", "PULLBACK"}:
            return RegimeAdjustment(regime, 5, 0, "Choppy market prefers pullbacks")
        return RegimeAdjustment(regime, -8, 5, "Choppy market stricter filtering")

    if regime == HIGH_VOL:
        return RegimeAdjustment(regime, -5, 5, "High volatility reduce aggression")

    if regime == LOW_VOL:
        return RegimeAdjustment(regime, -4, 3, "Low volatility reduce breakout chasing")

    return RegimeAdjustment(regime, 0, 0, "Mixed market no major adjustment")
