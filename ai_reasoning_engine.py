from __future__ import annotations

from typing import Dict, Any

from execution_quality import evaluate_execution_quality
from market_regime import detect_market_regime
from multi_timeframe_engine import analyze_multi_timeframe_structure
from setup_filters import evaluate_setup_quality
from vision_ai import score_chart_structure
from performance_learning import calibrate_confidence, priority_bonus, score_adjustment, setup_structure_key
from config import (
    ALLOW_EXECUTION_WARNING,
    ALLOW_MTF_MIXED,
    ALLOW_SETUP_WARNING,
    EARLY_SESSION_GRACE_ENABLED,
    EARLY_SESSION_MIN_SCORE_BUFFER,
    MIN_SCORE,
)


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
        regime = detect_market_regime(market or {}) or {}
    except Exception as e:
        regime = {
            "regime": "UNKNOWN",
            "confidence": 0,
            "reasons": [f"regime unavailable: {e}"],
        }

    return {
        "market": market or {},
        "regime": regime or {},
    }


def build_reasoning_report(
    ticker: str,
    setup: Dict[str, Any],
    tech: Dict[str, Any],
    bot=None,
    trade_type="INTRADAY",
) -> Dict[str, Any]:

    setup = setup or {}
    tech = tech or {}

    direction = setup.get("direction", "CALL")
    base_score = _safe_float(setup.get("score"), 0)

    context = _market_context(bot)
    regime = context.get("regime") or {}

    try:
        mtf = analyze_multi_timeframe_structure(tech, direction) or {}
    except Exception:
        mtf = {}

    try:
        execution = evaluate_execution_quality(tech) or {}
    except Exception:
        execution = {}

    try:
        setup_quality = evaluate_setup_quality(tech, direction) or {}
    except Exception:
        setup_quality = {}

    try:
        vision = score_chart_structure(tech, direction) or {}
    except Exception:
        vision = {}

    score = base_score
    early_session_setup = bool(setup.get("early_session_setup") or tech.get("early_session_setup")) and EARLY_SESSION_GRACE_ENABLED
    high_quality_floor = MIN_SCORE - EARLY_SESSION_MIN_SCORE_BUFFER if early_session_setup else MIN_SCORE
    high_quality_intraday = trade_type == "INTRADAY" and base_score >= high_quality_floor
    reasons = []
    warnings = []
    reject_reasons = []

    regime_name = regime.get("regime", "UNKNOWN")

    if regime_name in {"TRENDING_BULL", "TRENDING_BEAR"}:
        if (
            (direction == "CALL" and regime_name == "TRENDING_BULL")
            or (direction == "PUT" and regime_name == "TRENDING_BEAR")
        ):
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

    mtf_structure = mtf.get("structure")

    if mtf_structure == "STRONG_ALIGNMENT":
        score += 14
        reasons.append("Strong weekly/daily/intraday timeframe alignment")

    elif mtf_structure == "GOOD_ALIGNMENT":
        score += 8
        reasons.append("Good multi-timeframe alignment")

    elif mtf_structure == "MIXED_ALIGNMENT":
        if high_quality_intraday and ALLOW_MTF_MIXED:
            warnings.append("Mixed multi-timeframe alignment allowed for high-quality intraday setup")
        else:
            score -= 4
            warnings.append("Mixed multi-timeframe alignment")

    elif mtf_structure:
        score -= 16
        reject_reasons.append("Poor multi-timeframe alignment")

    ex_quality = execution.get("quality")

    if ex_quality == "GOOD":
        score += 10
        reasons.extend((execution.get("strengths") or [])[:2])

    elif ex_quality == "WARNING":
        if high_quality_intraday and ALLOW_EXECUTION_WARNING:
            warnings.append("Execution warning allowed for high-quality intraday setup")
        else:
            score -= 3
        warnings.extend((execution.get("warnings") or [])[:2])

    elif ex_quality:
        strong_intraday_mode = setup.get("entry_mode") in {"BREAKOUT", "RETEST", "MOMENTUM"}
        retest_or_approved = bool(setup.get("retest_confirmed") or setup.get("entry_mode") == "RETEST")
        if early_session_setup and high_quality_intraday:
            score -= 4
            warnings.append("Early-session liquidity warning allowed while volume/spread data is still forming")
            warnings.extend((execution.get("warnings") or [])[:3])
        elif high_quality_intraday and strong_intraday_mode and retest_or_approved:
            score -= 6
            warnings.append("Execution BAD softened for high-quality confirmed intraday setup")
            warnings.extend((execution.get("warnings") or [])[:3])
        else:
            score -= 18
            reject_reasons.append("Poor liquidity/execution quality")
            warnings.extend((execution.get("warnings") or [])[:3])

    filter_status = setup_quality.get("status")

    if filter_status == "PASS":
        score += 10
        reasons.extend((setup_quality.get("reasons") or [])[:2])

    elif filter_status == "WARNING":
        if high_quality_intraday and ALLOW_SETUP_WARNING:
            warnings.append("Setup warning allowed for high-quality intraday setup")
        else:
            score -= 4
        warnings.extend((setup_quality.get("warnings") or [])[:2])

    elif filter_status:
        if early_session_setup and high_quality_intraday:
            score -= 4
            warnings.append("Early-session setup warning allowed before full retest/structure criteria forms")
            warnings.extend((setup_quality.get("warnings") or [])[:3])
        else:
            score -= 18
            reject_reasons.append("Setup failed elite quality filters")
            warnings.extend((setup_quality.get("warnings") or [])[:3])

    vision_quality = vision.get("quality")

    if vision_quality == "ELITE":
        score += 12
        reasons.append("Chart structure is elite/clean")

    elif vision_quality == "GOOD":
        score += 7
        reasons.append("Chart structure is good")

    elif vision_quality == "POOR":
        score -= 15
        reject_reasons.append("Poor chart structure / late chase risk")
        warnings.extend((vision.get("warnings") or [])[:3])

    rr = _safe_float(
        setup.get("risk_reward"),
        _safe_float(tech.get("risk_reward"), 0),
    )

    if rr >= 2.0:
        score += 5
        reasons.append(f"Risk/reward acceptable: {rr:.2f}R")

    elif rr and rr < 1.5:
        score -= 10
        warnings.append(f"Risk/reward weak: {rr:.2f}R")

    learning_context = {
        "alert_type": trade_type,
        "entry_mode": setup.get("entry_mode", "SWING" if trade_type == "SWING" else "STANDARD"),
        "direction": direction,
        "market_regime": regime.get("regime"),
        "mtf_structure": mtf.get("structure"),
        "chart_structure": vision.get("quality"),
    }
    learning_context["setup_key"] = setup_structure_key(learning_context)

    learning_score_adjustment = score_adjustment(learning_context)
    learning_priority_bonus = priority_bonus(learning_context)
    if learning_score_adjustment:
        score += learning_score_adjustment
        reasons.append(f"Historical setup edge adjusted score by {learning_score_adjustment:+.1f}")
    elif learning_priority_bonus < 0:
        warnings.append("Historical setup performance is not yet favorable")

    confidence_seed = setup.get("confidence", setup.get("ml_probability", base_score))
    learning_confidence = calibrate_confidence(confidence_seed, learning_context)

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

    narrative = _build_narrative(
        ticker,
        trade_type,
        direction,
        decision,
        final_score,
        regime,
        mtf,
        execution,
        setup_quality,
        vision,
        reasons,
        warnings,
        reject_reasons,
        learning_confidence,
        learning_priority_bonus,
    )

    return {
        "decision": decision,
        "final_score": final_score,
        "base_score": base_score,
        "regime": regime or {},
        "mtf": mtf or {},
        "execution": execution or {},
        "setup_quality": setup_quality or {},
        "vision": vision or {},
        "reasons": reasons,
        "warnings": warnings,
        "reject_reasons": reject_reasons,
        "learning_context": learning_context,
        "learning_confidence": learning_confidence,
        "priority_bonus": learning_priority_bonus,
        "narrative": narrative,
    }


def _build_narrative(
    ticker,
    trade_type,
    direction,
    decision,
    final_score,
    regime,
    mtf,
    execution,
    setup_quality,
    vision,
    reasons,
    warnings,
    reject_reasons,
    learning_confidence=None,
    learning_priority_bonus=0,
):

    regime = regime or {}
    mtf = mtf or {}
    execution = execution or {}
    setup_quality = setup_quality or {}
    vision = vision or {}
    learning_confidence = learning_confidence or {}
    learning_stats = learning_confidence.get("learning_stats") or {}

    lines = [
        f"AI Reasoning: {trade_type} {direction} {ticker} classified as {decision} with composite score {final_score}/100.",
        f"Market regime: {regime.get('regime', 'UNKNOWN')} ({regime.get('confidence', 0)}% confidence).",
        f"MTF structure: {mtf.get('structure', 'UNKNOWN')} with {mtf.get('aligned_timeframes', 0)} aligned timeframes.",
        f"Execution quality: {execution.get('quality', 'UNKNOWN')} | Setup filter: {setup_quality.get('status', 'UNKNOWN')} | Chart structure: {vision.get('quality', 'UNKNOWN')}.",
    ]

    if learning_stats:
        lines.append(
            "Historical learning: "
            f"win rate {learning_stats.get('win_rate', 0) * 100:.1f}% over {learning_stats.get('closed', 0)} closed alerts; "
            f"forecast accuracy {learning_stats.get('forecast_accuracy', 0) * 100:.1f}%; "
            f"confidence {learning_confidence.get('base_confidence', 0):.1f}% -> {learning_confidence.get('calibrated_confidence', 0):.1f}%; "
            f"priority bonus {learning_priority_bonus:+.1f}."
        )

    if reasons:
        lines.append("Strengths: " + "; ".join(reasons[:6]) + ".")

    if warnings:
        lines.append("Warnings: " + "; ".join(warnings[:5]) + ".")

    if reject_reasons:
        lines.append("Reject risks: " + "; ".join(reject_reasons[:4]) + ".")

    return "\n".join(lines)


def should_send_reasoned_alert(report: Dict[str, Any], min_score=80) -> bool:
    report = report or {}

    if report.get("decision") == "REJECT":
        return False

    if report.get("final_score", 0) < min_score:
        return False

    return True
