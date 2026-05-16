from __future__ import annotations

from typing import Any, Dict

from bot_utils import safe_float
from market_phase import EXHAUSTION, FAKE_BREAKOUT, RANGE, TREND_DAY, OPEN_DRIVE, PULLBACK, BREAKOUT_BUILDING, LIQUIDITY_TRAP

ENSEMBLE_WEIGHTS = {
    "technical": 0.30,
    "vision": 0.25,
    "market_regime": 0.15,
    "structure": 0.15,
    "execution": 0.10,
    "learning": 0.05,
}


def _quality_score(value: Any, mapping: Dict[str, float], default: float = 50.0) -> float:
    return mapping.get(str(value or "").upper(), default)


def setup_decay_score(setup: Dict[str, Any] | None, tech: Dict[str, Any] | None) -> Dict[str, Any]:
    setup = setup or {}
    tech = tech or {}
    age = safe_float(setup.get("setup_age_minutes"), safe_float(tech.get("setup_age_minutes"), 0)) or 0
    trigger_distance = safe_float(setup.get("distance_from_trigger"), safe_float(tech.get("trigger_distance_pct"), 0)) or 0
    atr_extension = safe_float(setup.get("breakout_distance_atr"), safe_float(tech.get("atr_extension"), safe_float(tech.get("breakout_distance_atr"), 0))) or 0
    decay = 0
    reasons: list[str] = []
    if age >= 45:
        decay += 12
        reasons.append(f"setup age {age:.0f}m")
    elif age >= 25:
        decay += 6
        reasons.append(f"setup aging {age:.0f}m")
    if abs(trigger_distance) >= 2.0:
        decay += 10
        reasons.append(f"trigger distance {trigger_distance:.2f}%")
    if atr_extension >= 1.8:
        decay += 25
        reasons.append(f"breakout extended {atr_extension:.2f} ATR")
    elif atr_extension >= 1.2:
        decay += 12
        reasons.append(f"breakout extension {atr_extension:.2f} ATR")
    return {"decay": min(45, decay), "reasons": reasons, "setup_age_minutes": age, "atr_extension": atr_extension}


def no_trade_score(components: Dict[str, Any]) -> Dict[str, Any]:
    score = 0
    reasons: list[str] = []
    phase = (components.get("market_phase") or {}).get("phase")
    phase_confidence = safe_float((components.get("market_phase") or {}).get("confidence"), 0) or 0
    if phase in {FAKE_BREAKOUT, EXHAUSTION}:
        score += 25
        reasons.append(f"phase={phase}")
    elif phase == RANGE and phase_confidence >= 70:
        score += 18
        reasons.append(f"phase={phase}")
    if (components.get("execution") or {}).get("quality") == "BAD":
        score += 18
        reasons.append("poor execution/liquidity")
    if (components.get("setup_quality") or {}).get("status") == "REJECT":
        score += 18
        reasons.append("setup quality reject")
    if (components.get("vision") or {}).get("quality") == "POOR":
        score += 18
        reasons.append("poor visual structure")
    rr = safe_float(components.get("risk_reward"), 0) or 0
    if rr and rr < 1.3:
        score += 15
        reasons.append(f"low R/R {rr:.2f}R")
    decay = safe_float((components.get("setup_decay") or {}).get("decay"), 0) or 0
    if decay >= 20:
        score += decay * 0.6
        reasons.append("setup decay/chase risk")
    return {"score": round(min(100, score), 2), "reasons": reasons, "is_no_trade": score >= 50}


def component_scores(*, base_score: float, regime: Dict[str, Any], market_phase: Dict[str, Any], mtf: Dict[str, Any], execution: Dict[str, Any], setup_quality: Dict[str, Any], vision: Dict[str, Any], learning_confidence: Dict[str, Any]) -> Dict[str, float]:
    phase = market_phase.get("phase")
    regime_name = regime.get("regime")
    technical = max(0, min(100, base_score))
    vision_score = _quality_score(vision.get("quality"), {"ELITE": 96, "GOOD": 86, "NEUTRAL": 68, "POOR": 35}, 60)
    regime_score = _quality_score(regime_name, {"TRENDING_BULL": 82, "TRENDING_BEAR": 82, "CHOPPY": 45, "HIGH_VOL": 55, "LOW_VOL": 58, "MIXED": 62, "UNKNOWN": 70}, 65)
    if phase in {TREND_DAY, OPEN_DRIVE, PULLBACK, BREAKOUT_BUILDING, LIQUIDITY_TRAP}:
        regime_score = min(100, regime_score + 10)
    elif phase in {RANGE, FAKE_BREAKOUT, EXHAUSTION}:
        regime_score = max(0, regime_score - 15)
    mtf_score = _quality_score(mtf.get("structure"), {"STRONG_ALIGNMENT": 95, "GOOD_ALIGNMENT": 86, "MIXED_ALIGNMENT": 72, "POOR_ALIGNMENT": 35}, 68)
    setup_score = _quality_score(setup_quality.get("status"), {"PASS": 90, "WARNING": 76, "REJECT": 35}, 68)
    structure = (mtf_score + setup_score) / 2
    execution_score = _quality_score(execution.get("quality"), {"GOOD": 90, "WARNING": 76, "BAD": 35}, 68)
    learning_score = safe_float(learning_confidence.get("calibrated_confidence"), base_score) or base_score
    return {
        "technical": round(technical, 2),
        "vision": round(vision_score, 2),
        "market_regime": round(regime_score, 2),
        "structure": round(structure, 2),
        "execution": round(execution_score, 2),
        "learning": round(max(0, min(100, learning_score)), 2),
    }


def weighted_ensemble_score(scores: Dict[str, float], weights: Dict[str, float] | None = None) -> float:
    weights = weights or ENSEMBLE_WEIGHTS
    total_weight = sum(weights.values()) or 1
    return round(sum((safe_float(scores.get(name), 0) or 0) * weight for name, weight in weights.items()) / total_weight, 2)


def probability_profile(final_score: float, no_trade: Dict[str, Any], market_phase: Dict[str, Any], vision: Dict[str, Any]) -> Dict[str, float]:
    trap_base = safe_float(no_trade.get("score"), 0) * 0.005
    phase = market_phase.get("phase")
    if phase in {FAKE_BREAKOUT, EXHAUSTION, RANGE}:
        trap_base += 0.18
    if (vision.get("visual") or {}).get("reading", {}).get("features", {}).get("liquidity_grab"):
        trap_base += 0.08
    win_probability = max(0.05, min(0.92, 0.35 + (final_score / 100) * 0.55 - trap_base * 0.25))
    continuation = max(0.05, min(0.95, 0.30 + (final_score / 100) * 0.60))
    reversal = max(0.03, min(0.90, 0.90 - continuation + trap_base * 0.3))
    trap = max(0.02, min(0.90, 0.12 + trap_base))
    return {
        "win_probability": round(win_probability, 2),
        "trend_continuation_probability": round(continuation, 2),
        "reversal_probability": round(reversal, 2),
        "trap_probability": round(trap, 2),
    }


def alert_quality_rank(final_score: float, probabilities: Dict[str, float], no_trade: Dict[str, Any]) -> str:
    if no_trade.get("is_no_trade") or probabilities.get("trap_probability", 0) >= 0.45:
        return "NO_TRADE"
    if final_score >= 92 and probabilities.get("win_probability", 0) >= 0.78:
        return "S-Tier"
    if final_score >= 84:
        return "A-Tier"
    if final_score >= 74:
        return "B-Tier"
    return "LOW_EDGE"


def dynamic_min_score(regime: str | None, phase: str | None, base_min: int) -> int:
    threshold = int(base_min)
    if phase in {TREND_DAY, OPEN_DRIVE}:
        threshold -= 10
    elif phase in {PULLBACK, LIQUIDITY_TRAP, BREAKOUT_BUILDING}:
        threshold -= 6
    elif phase in {RANGE, FAKE_BREAKOUT, EXHAUSTION}:
        threshold += 6
    if str(regime or "").upper() == "CHOPPY":
        threshold += 6
    elif str(regime or "").upper() in {"TRENDING_BULL", "TRENDING_BEAR"}:
        threshold -= 4
    return max(70, min(98, threshold))
