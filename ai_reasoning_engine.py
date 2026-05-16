from __future__ import annotations

from typing import Dict, Any

from execution_quality import evaluate_execution_quality
from market_regime import detect_market_regime
from market_phase import detect_market_phase, phase_score_adjustment
from ensemble_confidence import (
    alert_quality_rank,
    component_scores,
    dynamic_min_score,
    no_trade_score,
    probability_profile,
    setup_decay_score,
    weighted_ensemble_score,
)
from multi_timeframe_engine import analyze_multi_timeframe_structure
from setup_filters import evaluate_setup_quality
from vision_ai import score_chart_structure
from performance_learning import calibrate_confidence, priority_bonus, score_adjustment, setup_structure_key
from sector_filter import sector_direction_adjustment
from adaptive_scoring import behavior_penalty
from probabilistic_quality import DEFAULT_PENALTIES, classify_score, probabilistic_penalty_profile
from trade_attribution import setup_attribution_adjustment
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

    market_phase = detect_market_phase(tech, setup, context.get("market"))
    phase_adjustment = phase_score_adjustment(market_phase.get("phase"), setup.get("entry_mode"))
    if phase_adjustment:
        score += phase_adjustment
        target = reasons if phase_adjustment > 0 else warnings
        target.append(f"Market phase {market_phase.get('phase')} adjusted score by {phase_adjustment:+d}")

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
            score += DEFAULT_PENALTIES["mtf_mixed"]
            warnings.append("Mixed multi-timeframe alignment converted to small probability penalty")

    elif mtf_structure:
        score += DEFAULT_PENALTIES["mtf_poor"]
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
            score += DEFAULT_PENALTIES["execution_bad"]
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
            score += DEFAULT_PENALTIES["setup_reject"]
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
        score += DEFAULT_PENALTIES["vision_poor"]
        reject_reasons.append("Poor chart structure / late chase risk")
        warnings.extend((vision.get("warnings") or [])[:3])

    sector_context = tech.get("sector_relative_strength")
    if isinstance(sector_context, dict):
        sector_adjustment = sector_direction_adjustment(ticker, direction, sector_context)
        if sector_adjustment.get("adjustment"):
            score += sector_adjustment["adjustment"]
            target = reasons if sector_adjustment["adjustment"] > 0 else warnings
            target.append(f"Sector relative strength adjusted score by {sector_adjustment['adjustment']:+d}: {sector_adjustment.get('reason')}")
    else:
        sector_adjustment = {}

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

    attribution = setup_attribution_adjustment(learning_context["setup_key"])
    if attribution.get("adjustment"):
        score += attribution["adjustment"]
        target = reasons if attribution["adjustment"] > 0 else warnings
        target.append(f"Setup attribution adjusted score by {attribution['adjustment']:+d}: {attribution.get('reason')}")

    learning_score_adjustment = score_adjustment(learning_context)
    learning_priority_bonus = priority_bonus(learning_context)
    if learning_score_adjustment:
        score += learning_score_adjustment
        reasons.append(f"Historical setup edge adjusted score by {learning_score_adjustment:+.1f}")
    elif learning_priority_bonus < 0:
        warnings.append("Historical setup performance is not yet favorable")

    confidence_seed = setup.get("confidence", setup.get("ml_probability", base_score))
    learning_confidence = calibrate_confidence(confidence_seed, learning_context)

    adaptive_behavior_adjustment = behavior_penalty({
        "late_breakout_risk": setup.get("late_breakout_risk"),
        "atr_extension": tech.get("atr_extension") or tech.get("breakout_distance_atr"),
        "market_phase": market_phase.get("phase"),
        "risk_reward": setup.get("risk_reward") or tech.get("risk_reward"),
    })
    if adaptive_behavior_adjustment:
        score += adaptive_behavior_adjustment
        target = reasons if adaptive_behavior_adjustment > 0 else warnings
        target.append(f"Adaptive ML behavior adjusted score by {adaptive_behavior_adjustment:+d}")

    setup_decay = setup_decay_score(setup, tech)
    if setup_decay.get("decay"):
        score -= setup_decay["decay"]
        warnings.append("Setup decay penalty: " + ", ".join(setup_decay.get("reasons") or []))

    probabilistic_profile = probabilistic_penalty_profile(
        execution=execution,
        setup_quality=setup_quality,
        mtf=mtf,
        vision=vision,
    )
    if probabilistic_profile.get("reasons"):
        warnings.append("Probabilistic penalties: " + ", ".join(probabilistic_profile["reasons"][:5]))

    raw_final_score = max(0, min(100, round(score, 2)))
    ensemble_components = component_scores(
        base_score=base_score,
        regime=regime,
        market_phase=market_phase,
        mtf=mtf,
        execution=execution,
        setup_quality=setup_quality,
        vision=vision,
        learning_confidence=learning_confidence,
    )
    ensemble_score = weighted_ensemble_score(ensemble_components)
    # Preserve proven high-confluence rule strength while exposing the weighted
    # ensemble as the calibration backbone. Hard reject reasons become score
    # penalties/no-trade risk rather than automatic rejection.
    final_score = max(raw_final_score, ensemble_score)
    no_trade = no_trade_score({
        "market_phase": market_phase,
        "execution": execution,
        "setup_quality": setup_quality,
        "vision": vision,
        "risk_reward": rr,
        "setup_decay": setup_decay,
    })
    if no_trade.get("score"):
        final_score = max(0, round(final_score - min(20, no_trade["score"] * 0.2), 2))
        if no_trade.get("reasons"):
            warnings.append("No-trade risk: " + ", ".join(no_trade["reasons"][:4]))

    probabilities = probability_profile(final_score, no_trade, market_phase, vision)
    quality_rank = alert_quality_rank(final_score, probabilities, no_trade)
    probabilistic_tier = classify_score(final_score)
    adaptive_min_score = dynamic_min_score(regime_name, market_phase.get("phase"), MIN_SCORE)

    if no_trade.get("is_no_trade") and final_score < 90:
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
        market_phase=market_phase,
        ensemble_score=ensemble_score,
        component_scores=ensemble_components,
        probabilities=probabilities,
        quality_rank=quality_rank,
        adaptive_min_score=adaptive_min_score,
        probabilistic_tier=probabilistic_tier,
        no_trade=no_trade,
    )

    return {
        "decision": decision,
        "final_score": final_score,
        "base_score": base_score,
        "regime": regime or {},
        "market_phase": market_phase or {},
        "mtf": mtf or {},
        "execution": execution or {},
        "setup_quality": setup_quality or {},
        "vision": vision or {},
        "ensemble_score": ensemble_score,
        "component_scores": ensemble_components,
        "setup_decay": setup_decay,
        "no_trade": no_trade,
        "probabilities": probabilities,
        "quality_rank": quality_rank,
        "probabilistic_tier": probabilistic_tier,
        "adaptive_min_score": adaptive_min_score,
        "sector_relative_strength": sector_adjustment,
        "adaptive_behavior_adjustment": adaptive_behavior_adjustment,
        "setup_attribution": attribution,
        "probabilistic_penalties": probabilistic_profile,
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
    market_phase=None,
    ensemble_score=None,
    component_scores=None,
    probabilities=None,
    quality_rank=None,
    adaptive_min_score=None,
    probabilistic_tier=None,
    no_trade=None,
):

    regime = regime or {}
    mtf = mtf or {}
    execution = execution or {}
    setup_quality = setup_quality or {}
    vision = vision or {}
    learning_confidence = learning_confidence or {}
    learning_stats = learning_confidence.get("learning_stats") or {}
    market_phase = market_phase or {}
    component_scores = component_scores or {}
    probabilities = probabilities or {}
    no_trade = no_trade or {}

    lines = [
        f"AI Reasoning: {trade_type} {direction} {ticker} classified as {decision} with composite score {final_score}/100.",
        f"Market regime: {regime.get('regime', 'UNKNOWN')} ({regime.get('confidence', 0)}% confidence).",
        f"Market phase: {market_phase.get('phase', 'UNKNOWN')} ({market_phase.get('confidence', 0)}% confidence); adaptive minimum score {adaptive_min_score or 'n/a'}.",
        f"MTF structure: {mtf.get('structure', 'UNKNOWN')} with {mtf.get('aligned_timeframes', 0)} aligned timeframes.",
        f"Execution quality: {execution.get('quality', 'UNKNOWN')} | Setup filter: {setup_quality.get('status', 'UNKNOWN')} | Chart structure: {vision.get('quality', 'UNKNOWN')}.",
        f"Weighted ensemble: {ensemble_score if ensemble_score is not None else 'n/a'} with components {component_scores}; rank {quality_rank or 'n/a'}; probabilistic tier {probabilistic_tier or 'n/a'}.",
        f"Probabilities: win {probabilities.get('win_probability', 0):.2f}, continuation {probabilities.get('trend_continuation_probability', 0):.2f}, reversal {probabilities.get('reversal_probability', 0):.2f}, trap {probabilities.get('trap_probability', 0):.2f}.",
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

    if no_trade.get("score"):
        lines.append(f"No-trade score: {no_trade.get('score')}/100 from {'; '.join(no_trade.get('reasons') or [])}.")

    if reject_reasons:
        lines.append("Reject risks converted to penalties: " + "; ".join(reject_reasons[:4]) + ".")

    return "\n".join(lines)


def should_send_reasoned_alert(report: Dict[str, Any], min_score=80) -> bool:
    report = report or {}

    if report.get("decision") == "REJECT":
        return False

    if report.get("final_score", 0) < min_score:
        return False

    return True
