from __future__ import annotations

from typing import Dict, Any

from execution_quality import evaluate_execution_quality
from market_regime import detect_market_regime
from multi_timeframe_engine import analyze_multi_timeframe_structure
from setup_filters import evaluate_setup_quality
from vision_ai import score_chart_structure


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _market_context(bot=None) -> Dict[str, Any]:
    try:
        market = bot.get_market_bias() if bot else {}
    except Exception:
        market = {}
    try:
        regime = detect_market_regime(market or {})
    except Exception as e:
        regime = {"regime": "UNKNOWN", "confidence": 0, "reasons": [f"regime unavailable: {e}"]}
    return {"market": market or {}, "regime": regime}


def build_reasoning_report(ticker: str, setup: Dict[str, Any], tech: Dict[str, Any], bot=None, trade_type="INTRADAY") -> Dict[str, Any]:
    direction = setup.get("direction", "CALL")
    base_score = _safe_float(setup.get("score"), 0)

    context = _market_context(bot)
    regime = context["regime"]

    mtf = analyze_multi_timeframe_structure(tech, direction)
    execution = evaluate_execution_quality(tech)
    setup_quality = evaluate_setup_quality(tech, direction)
    vision = score_chart_structure(tech, direction)

    score = base_score
    reasons = []
    warnings = []
    reject_reasons = []

    # Market regime contribution
    regime_name = regime.get("regime", "UNKNOWN")
    if regime_name in {"TRENDING_BULL", "TRENDING_BEAR"}:
        if (direction == "CALL" and regime_name == "TRENDING_BULL") or (direction == "PUT" and regime_name == "TRENDING_BEAR"):
            score += 8
            reasons.append(f"Market regime aligned: {regime_name}")
        else:
            score -= 12
            warnings.append(f"Trade direction conflicts with regime: {regime_name}")
    elif regime_name == "CHOPPY":
        if setup.get("entry_mode") in {"BREAKOUT", "MOMENTUM"}:
            score -= 12
            warnings.append("Choppy regime penalizes breakout/momentum entries")
        else:
            score -= 4
            warnings.append("Choppy regime requires cleaner confirmation")
    elif regime_name == "HIGH_VOL":
        score -= 6
        warnings.append("High-volatility regime: reduce aggressiveness")

    # Multi-timeframe structure
    mtf_structure = mtf.get("structure")
    if mtf_structure == "STRONG_ALIGNMENT":
        score += 14
        reasons.append("Strong weekly/daily/intraday timeframe alignment")
    elif mtf_structure == "GOOD_ALIGNMENT":
        score += 8
        reasons.append("Good multi-timeframe alignment")
    elif mtf_structure == "MIXED_ALIGNMENT":
        score -= 4
        warnings.append("Mixed multi-timeframe alignment")
    else:
        score -= 16
        reject_reasons.append("Poor multi-timeframe alignment")

    # Execution and liquidity
    ex_quality = execution.get("quality")
    if ex_quality == "GOOD":
        score += 10
        reasons.extend(execution.get("strengths", [])[:2])
    elif ex_quality == "WARNING":
        score -= 3
        warnings.extend(execution.get("warnings", [])[:2])
    else:
        score -= 18
        reject_reasons.append("Poor liquidity/execution quality")
        warnings.extend(execution.get("warnings", [])[:3])

    # Elite setup filters
    filter_status = setup_quality.get("status")
    if filter_status == "PASS":
        score += 10
        reasons.extend(setup_quality.get("reasons", [])[:2])
    elif filter_status == "WARNING":
        score -= 4
        warnings.extend(setup_quality.get("warnings", [])[:2])
    else:
        score -= 18
        reject_reasons.append("Setup failed elite quality filters")
        warnings.extend(setup_quality.get("warnings", [])[:3])

    # Vision-style structure scoring
    vision_quality = vision.get("quality")
    if vision_quality == "ELITE":
        score += 12
        reasons.append("Chart structure is elite/clean")
    elif vision_quality == "GOOD":
        score += 7
        reasons.append("Chart structure is good")
    elif vision_quality == "NEUTRAL":
        score += 0
    else:
        score -= 15
        reject_reasons.append("Poor chart structure / late chase risk")
        warnings.extend(vision.get("warnings", [])[:3])

    rr = _safe_float(setup.get("risk_reward"), _safe_float(tech.get("risk_reward"), 0))
    if rr >= 2.0:
        score += 5
        reasons.append(f"Risk/reward acceptable: {rr:.2f}R")
    elif rr and rr < 1.5:
        score -= 10
        warnings.append(f"Risk/reward weak: {rr:.2f}R")

    final_score = max(0, min(100, round(score, 2)))
    if reject_reasons and final_score < 85:
        decision = "REJECT"
    elif final_score >= 90:
        decision = "A+"
    elif final_score >= 80:
        decision = "A"
    elif final_score >= 70:
        decision = "WATCH"
    else:
        decision = "REJECT"

    narrative = _build_narrative(ticker, trade_type, direction, decision, final_score, regime, mtf, execution, setup_quality, vision, reasons, warnings, reject_reasons)

    return {
        "decision": decision,
        "final_score": final_score,
        "base_score": base_score,
        "regime": regime,
        "mtf": mtf,
        "execution": execution,
        "setup_quality": setup_quality,
        "vision": vision,
        "reasons": reasons,
        "warnings": warnings,
        "reject_reasons": reject_reasons,
        "narrative": narrative,
    }


def _build_narrative(ticker, trade_type, direction, decision, final_score, regime, mtf, execution, setup_quality, vision, reasons, warnings, reject_reasons):
    lines = [
        f"AI Reasoning: {trade_type} {direction} {ticker} classified as {decision} with composite score {final_score}/100.",
        f"Market regime: {regime.get('regime')} ({regime.get('confidence')}% confidence).",
        f"MTF structure: {mtf.get('structure')} with {mtf.get('aligned_timeframes')} aligned timeframes.",
        f"Execution quality: {execution.get('quality')} | Setup filter: {setup_quality.get('status')} | Chart structure: {vision.get('quality')}.",
    ]
    if reasons:
        lines.append("Strengths: " + "; ".join(reasons[:6]) + ".")
    if warnings:
        lines.append("Warnings: " + "; ".join(warnings[:5]) + ".")
    if reject_reasons:
        lines.append("Reject risks: " + "; ".join(reject_reasons[:4]) + ".")
    return "\n".join(lines)


def should_send_reasoned_alert(report: Dict[str, Any], min_score=80) -> bool:
    if report.get("decision") == "REJECT":
        return False
    if report.get("final_score", 0) < min_score:
        return False
    return True
