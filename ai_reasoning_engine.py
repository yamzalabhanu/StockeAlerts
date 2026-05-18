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
from performance_learning import calibrate_confidence, priority_bonus, score_adjustment, setup_structure_key, similar_context_memory
from sector_filter import sector_direction_adjustment
from adaptive_scoring import behavior_penalty
from probabilistic_quality import DEFAULT_PENALTIES, classify_score, probabilistic_penalty_profile
from trade_attribution import setup_attribution_adjustment
from risk_utils import phase5_execution_plan
from config import (
    ALLOW_EXECUTION_WARNING,
    ALLOW_MTF_MIXED,
    ALLOW_SETUP_WARNING,
    EARLY_SESSION_GRACE_ENABLED,
    EARLY_SESSION_MIN_SCORE_BUFFER,
    MIN_SCORE,
    ACCOUNT_SIZE,
    RISK_PER_TRADE_PCT,
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


def _as_mapping(value):
    if isinstance(value, dict):
        return value
    return getattr(value, "__dict__", {}) or {}


def _first_context_value(setup: Dict[str, Any], tech: Dict[str, Any], *names: str):
    for name in names:
        if name in setup and setup.get(name) not in (None, ""):
            return setup.get(name)
        if name in tech and tech.get(name) not in (None, ""):
            return tech.get(name)
    return None


def _option_analysis(ticker: str, direction: str, setup: Dict[str, Any], tech: Dict[str, Any]) -> Dict[str, Any]:
    """Convert available options flow/contract data into adaptive reasoning inputs."""
    flow = _as_mapping(setup.get("options_flow") or tech.get("options_flow"))
    contract = _as_mapping(setup.get("option_contract") or tech.get("option_contract"))
    reasons: list[str] = []
    warnings: list[str] = []
    score_adjustment = 0.0

    direction = str(direction or "").upper()
    expected_bias = "BULLISH" if direction == "CALL" else "BEARISH" if direction == "PUT" else None

    if flow:
        status = flow.get("status")
        bias = flow.get("bias")
        flow_score = _safe_float(flow.get("score"), 0)
        if status and status != "OK":
            warnings.append(f"Options flow unavailable ({status}: {flow.get('reason', 'no reason supplied')})")
        elif expected_bias and bias == expected_bias:
            adjustment = min(8, max(2, (flow_score - 50) * 0.12)) if flow_score >= 50 else 1
            score_adjustment += adjustment
            reasons.append(f"Options flow confirms {direction} bias: {bias} {flow_score:.0f}/100")
        elif bias in {"BULLISH", "BEARISH"} and expected_bias and bias != expected_bias:
            score_adjustment -= 10
            warnings.append(f"Options flow conflicts with {direction}: {bias} {flow_score:.0f}/100")
        elif flow_score:
            warnings.append(f"Options flow is neutral/mixed at {flow_score:.0f}/100")

        if flow.get("gamma_squeeze") and direction == "CALL":
            score_adjustment += 4
            reasons.append("Gamma-squeeze conditions support call continuation")
        dealer_gamma = flow.get("dealer_gamma_state")
        if dealer_gamma == "SHORT_GAMMA":
            warnings.append("Short-gamma dealer state can amplify volatility; use tighter execution discipline")

        signals = flow.get("signals") or []
        if isinstance(signals, list) and signals:
            signal_names = []
            for signal in signals[:3]:
                data = _as_mapping(signal)
                if data.get("name"):
                    signal_names.append(str(data.get("name")))
            if signal_names:
                reasons.append("Top options signals: " + ", ".join(signal_names))

    if contract:
        status = contract.get("status")
        if status and status != "OK":
            warnings.append(f"Option contract not order-ready ({status}: {contract.get('reason', 'no reason supplied')})")
        elif not status or status == "OK":
            spread = _safe_float(contract.get("spread_pct"), None)
            volume = _safe_float(contract.get("volume"), 0)
            oi = _safe_float(contract.get("open_interest"), 0)
            rec_score = _safe_float(contract.get("recommendation_score"), 0)
            delta = _safe_float(contract.get("delta"), None)
            dte = _safe_float(contract.get("dte"), None)
            iv = _safe_float(contract.get("implied_volatility"), None)
            symbol = contract.get("contract_symbol") or f"{ticker} option"

            if rec_score >= 70:
                score_adjustment += min(5, rec_score * 0.04)
                reasons.append(f"Recommended contract {symbol} has strong liquidity score {rec_score:.0f}/100")
            elif rec_score:
                warnings.append(f"Recommended contract liquidity score is only {rec_score:.0f}/100")

            if spread is not None:
                if spread <= 12:
                    score_adjustment += 2
                    reasons.append(f"Option spread is tradable at {spread:.1f}%")
                else:
                    score_adjustment -= 5
                    warnings.append(f"Option spread is wide at {spread:.1f}%")

            if volume >= 50 and oi >= 100:
                reasons.append(f"Option liquidity supports execution: volume {volume:.0f}, OI {oi:.0f}")
            elif volume or oi:
                warnings.append(f"Option liquidity is thin: volume {volume:.0f}, OI {oi:.0f}")

            if delta is not None:
                abs_delta = abs(delta)
                if 0.35 <= abs_delta <= 0.65:
                    reasons.append(f"Delta {delta:.2f} gives directional exposure without extreme moneyness")
                else:
                    warnings.append(f"Delta {delta:.2f} is outside the preferred directional range")
            if dte is not None:
                if dte < 5:
                    warnings.append(f"Only {dte:.0f} DTE remains; theta/gamma risk is elevated")
                else:
                    reasons.append(f"{dte:.0f} DTE leaves time for the thesis to work")
            if iv is not None and iv > 1.2:
                warnings.append(f"IV {iv:.2f} is elevated; avoid overpaying premium")

    return {
        "score_adjustment": round(score_adjustment, 2),
        "reasons": reasons,
        "warnings": warnings,
        "flow": flow,
        "contract": contract,
    }


def _technical_context(setup: Dict[str, Any], tech: Dict[str, Any], direction: str) -> Dict[str, Any]:
    price = _first_context_value(setup, tech, "price", "entry")
    ema_fast = _first_context_value(setup, tech, "ema9", "ema8")
    ema_mid = _first_context_value(setup, tech, "ema21")
    ema_slow = _first_context_value(setup, tech, "ema50")
    vwap = _first_context_value(setup, tech, "vwap")
    orb_high = _first_context_value(setup, tech, "orb_high")
    orb_low = _first_context_value(setup, tech, "orb_low")
    rel_volume = _first_context_value(setup, tech, "relative_volume", "rel_volume", "volume_ratio")
    atr_extension = _first_context_value(setup, tech, "atr_extension", "breakout_distance_atr")

    price_f = _safe_float(price, None)
    fast_f = _safe_float(ema_fast, None)
    mid_f = _safe_float(ema_mid, None)
    slow_f = _safe_float(ema_slow, None)
    vwap_f = _safe_float(vwap, None)
    orb_high_f = _safe_float(orb_high, None)
    orb_low_f = _safe_float(orb_low, None)

    observations: list[str] = []
    if price_f is not None and fast_f is not None and mid_f is not None:
        if direction == "CALL" and price_f >= fast_f >= mid_f:
            observations.append(f"price {price_f:.2f} is stacked above fast/mid EMAs ({fast_f:.2f}/{mid_f:.2f})")
        elif direction == "PUT" and price_f <= fast_f <= mid_f:
            observations.append(f"price {price_f:.2f} is stacked below fast/mid EMAs ({fast_f:.2f}/{mid_f:.2f})")
        else:
            observations.append(f"EMA stack is mixed around price {price_f:.2f} (fast {fast_f:.2f}, mid {mid_f:.2f})")
    if slow_f is not None:
        observations.append(f"EMA50 reference {slow_f:.2f}")
    if price_f is not None and vwap_f is not None:
        if direction == "CALL" and price_f >= vwap_f:
            observations.append(f"price is holding above VWAP {vwap_f:.2f}")
        elif direction == "PUT" and price_f <= vwap_f:
            observations.append(f"price is holding below VWAP {vwap_f:.2f}")
        else:
            observations.append(f"price is on the wrong side of VWAP {vwap_f:.2f} for {direction}")
    if price_f is not None and orb_high_f is not None and direction == "CALL":
        observations.append(f"distance to ORB high {orb_high_f:.2f}: {price_f - orb_high_f:+.2f}")
    if price_f is not None and orb_low_f is not None and direction == "PUT":
        observations.append(f"distance to ORB low {orb_low_f:.2f}: {price_f - orb_low_f:+.2f}")
    if rel_volume not in (None, ""):
        observations.append(f"relative volume {rel_volume}x")
    if atr_extension not in (None, ""):
        observations.append(f"ATR extension {atr_extension}")

    return {
        "price": price_f,
        "ema_fast": fast_f,
        "ema_mid": mid_f,
        "ema_slow": slow_f,
        "vwap": vwap_f,
        "orb_high": orb_high_f,
        "orb_low": orb_low_f,
        "relative_volume": rel_volume,
        "atr_extension": atr_extension,
        "observations": observations,
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

    technical_context = _technical_context(setup, tech, direction)
    options_analysis = _option_analysis(ticker, direction, setup, tech)

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

    option_score_adjustment = _safe_float(options_analysis.get("score_adjustment"), 0)
    if option_score_adjustment:
        score += option_score_adjustment
        target = reasons if option_score_adjustment > 0 else warnings
        target.append(f"Options analysis adjusted score by {option_score_adjustment:+.1f}")
    reasons.extend((options_analysis.get("reasons") or [])[:5])
    warnings.extend((options_analysis.get("warnings") or [])[:5])

    learning_context = {
        "alert_type": trade_type,
        "entry_mode": setup.get("entry_mode", "SWING" if trade_type == "SWING" else "STANDARD"),
        "direction": direction,
        "market_regime": regime.get("regime"),
        "market_phase": market_phase.get("phase"),
        "session_time_bucket": tech.get("session_time_bucket") or setup.get("session_time_bucket"),
        "mtf_structure": mtf.get("structure"),
        "chart_structure": vision.get("quality"),
        "option_spread_pct": setup.get("option_spread_pct") or tech.get("option_spread_pct"),
        "option_volume": setup.get("option_volume") or tech.get("option_volume"),
        "option_open_interest": setup.get("option_open_interest") or tech.get("option_open_interest"),
    }
    learning_context["setup_key"] = setup_structure_key(learning_context)

    attribution = setup_attribution_adjustment(learning_context["setup_key"])
    if attribution.get("adjustment"):
        score += attribution["adjustment"]
        target = reasons if attribution["adjustment"] > 0 else warnings
        target.append(f"Setup attribution adjusted score by {attribution['adjustment']:+d}: {attribution.get('reason')}")

    learning_score_adjustment = score_adjustment(learning_context)
    context_memory = similar_context_memory(learning_context)
    if context_memory.get("score_adjustment"):
        score += context_memory["score_adjustment"]
        target = reasons if context_memory["score_adjustment"] > 0 else warnings
        target.append(f"Phase 4 similar-context memory adjusted score by {context_memory['score_adjustment']:+.1f}: {context_memory.get('reason')}")
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
    risk_plan = phase5_execution_plan(
        final_score=final_score,
        probabilities=probabilities,
        no_trade=no_trade,
        execution=execution,
        setup=setup,
        tech=tech,
        account_size=ACCOUNT_SIZE,
        base_risk_pct=RISK_PER_TRADE_PCT,
    )
    if risk_plan.get("action") == "WATCH_ONLY" and final_score < 92:
        warnings.append("Phase 5 risk plan downgraded execution to watch-only")

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
        context_memory=context_memory,
        risk_plan=risk_plan,
        technical_context=technical_context,
        options_analysis=options_analysis,
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
        "context_memory": context_memory,
        "risk_plan": risk_plan,
        "technical_context": technical_context,
        "options_analysis": options_analysis,
        "reasons": reasons,
        "warnings": warnings,
        "reject_reasons": reject_reasons,
        "learning_context": learning_context,
        "learning_confidence": learning_confidence,
        "priority_bonus": learning_priority_bonus,
        "narrative": narrative,
    }


def _direction_label(direction):
    direction = str(direction or "").upper()
    if direction == "PUT":
        return "bearish"
    if direction == "CALL":
        return "bullish"
    return "directional"


def _chart_quality_label(quality):
    quality = str(quality or "").upper()
    if quality == "ELITE":
        return "Very strong"
    if quality == "GOOD":
        return "Strong"
    if quality == "POOR":
        return "Weak"
    return "Unclear"


def _market_support_label(direction, regime_name):
    direction = str(direction or "").upper()
    regime_name = str(regime_name or "").upper()
    aligned = (
        (direction == "CALL" and regime_name == "TRENDING_BULL")
        or (direction == "PUT" and regime_name == "TRENDING_BEAR")
    )
    if aligned:
        return "Strong"
    if regime_name in {"TRENDING_BULL", "TRENDING_BEAR"}:
        return "Weak/conflicting"
    if regime_name in {"CHOPPY", "HIGH_VOL"}:
        return "Mixed/cautious"
    return "Unclear"


def _options_confirmation_label(options_reasons, options_warnings):
    warning_text = " ".join(str(warning) for warning in options_warnings).lower()
    has_conflict = "conflicts" in warning_text or "not order-ready" in warning_text
    if has_conflict:
        return "Weak/conflicting"
    if options_reasons and not options_warnings:
        return "Strong"
    if options_reasons and options_warnings:
        return "Mixed"
    if options_warnings:
        return "Weak"
    return "Unclear"


def _entry_quality_label(execution_quality, setup_status):
    execution_quality = str(execution_quality or "").upper()
    setup_status = str(setup_status or "").upper()
    if execution_quality == "GOOD" and setup_status == "PASS":
        return "Clean"
    if execution_quality in {"WARNING", "BAD"} or setup_status in {"WARNING", "REJECT"}:
        return "Not ideal"
    return "Unclear"


def _trade_status_label(risk_plan, setup_status, options_confirmation, no_trade):
    action = str((risk_plan or {}).get("action") or "").upper()
    setup_status = str(setup_status or "").upper()
    if action == "WATCH_ONLY" or (no_trade or {}).get("is_no_trade"):
        return "Watch only / possibly skip"
    if setup_status == "REJECT" or options_confirmation in {"Weak/conflicting", "Weak"}:
        if action == "REDUCED_SIZE":
            return "Caution / reduced size / possibly skip"
        return "Caution / possibly skip"
    if action == "REDUCED_SIZE":
        return "Reduced size"
    if action:
        return action.replace("_", " ").title()
    return "Caution"


def _best_action_label(setup_status, options_confirmation, execution_quality):
    setup_status = str(setup_status or "").upper()
    execution_quality = str(execution_quality or "").upper()
    if setup_status == "REJECT" or options_confirmation in {"Weak/conflicting", "Weak"}:
        return "Wait for cleaner confirmation or a better option contract"
    if execution_quality == "WARNING" or setup_status == "WARNING":
        return "Wait for a cleaner entry trigger, or take reduced size with strict risk control"
    return "Proceed only if price confirms the thesis and risk/reward remains acceptable"


def _primary_quality_issue(setup_status, options_confirmation, execution_quality):
    setup_status = str(setup_status or "").upper()
    execution_quality = str(execution_quality or "").upper()
    issues = []
    if setup_status == "REJECT":
        issues.append("the setup filter rejected it")
    elif setup_status == "WARNING":
        issues.append("the setup filter only gave a warning")
    if options_confirmation == "Weak/conflicting":
        issues.append("options flow conflicts with the idea or the contract is not order-ready")
    elif options_confirmation == "Weak":
        issues.append("options confirmation is weak")
    if execution_quality == "WARNING":
        issues.append("entry quality is not ideal")
    elif execution_quality == "BAD":
        issues.append("execution quality is poor")
    if not issues:
        issues.append("it still needs live price confirmation")
    if len(issues) == 1:
        return issues[0]
    return ", ".join(issues[:-1]) + ", and " + issues[-1]


def _build_human_readable_summary(
    ticker,
    direction,
    mtf,
    execution,
    setup_quality,
    vision,
    regime,
    options_reasons,
    options_warnings,
    risk_plan,
    no_trade,
):
    bias_word = _direction_label(direction)
    idea_direction = f"{bias_word} {ticker} {str(direction or '').lower()} idea".strip()
    mtf_structure = str((mtf or {}).get("structure") or "").upper()
    chart_quality = _chart_quality_label((vision or {}).get("quality"))
    technical_alignment = (
        "strong technical alignment"
        if mtf_structure in {"STRONG_ALIGNMENT", "GOOD_ALIGNMENT"}
        else "mixed technical alignment"
    )
    options_confirmation = _options_confirmation_label(options_reasons, options_warnings)
    execution_quality = (execution or {}).get("quality")
    setup_status = (setup_quality or {}).get("status")
    entry_quality = _entry_quality_label(execution_quality, setup_status)
    market_support = _market_support_label(direction, (regime or {}).get("regime"))
    trade_status = _trade_status_label(risk_plan, setup_status, options_confirmation, no_trade)
    best_action = _best_action_label(setup_status, options_confirmation, execution_quality)
    quality_issue = _primary_quality_issue(setup_status, options_confirmation, execution_quality)

    conclusion = (
        f"This is a {idea_direction} with {technical_alignment} "
        f"but {options_confirmation.lower()} execution confirmation."
    )
    approval_sentence = (
        "The model likes the direction, but not the trade quality enough to fully approve it."
        if trade_status.lower().startswith(("caution", "watch")) or entry_quality == "Not ideal"
        else "The model likes both the direction and the current trade quality, but it still requires disciplined risk control."
    )
    one_sentence = (
        f"{ticker} looks {bias_word} and the model sees strong "
        f"{('downside' if str(direction).upper() == 'PUT' else 'upside')} potential, "
        f"but the trade is not clean enough because {quality_issue}."
    )

    return "\n".join([
        "Best human-readable conclusion",
        "",
        conclusion,
        "",
        approval_sentence,
        "Practical interpretation",
        "",
        "I would summarize it as:",
        "",
        f"Bias: {bias_word.title()}",
        f"Chart quality: {chart_quality}",
        f"Market support: {market_support}",
        f"Options confirmation: {options_confirmation}",
        f"Entry quality: {entry_quality}",
        f"Trade status: {trade_status}",
        f"Best action: {best_action}",
        "One-sentence summary",
        "",
        one_sentence,
    ])

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
    context_memory=None,
    risk_plan=None,
    technical_context=None,
    options_analysis=None,
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
    context_memory = context_memory or {}
    risk_plan = risk_plan or {}
    technical_context = technical_context or {}
    options_analysis = options_analysis or {}

    tech_observations = technical_context.get("observations") or []
    options_reasons = options_analysis.get("reasons") or []
    options_warnings = options_analysis.get("warnings") or []
    option_flow = options_analysis.get("flow") or {}
    option_contract = options_analysis.get("contract") or {}

    take_trade_parts = []
    if mtf.get("structure") in {"STRONG_ALIGNMENT", "GOOD_ALIGNMENT"}:
        take_trade_parts.append("timeframes are aligned")
    if vision.get("quality") in {"ELITE", "GOOD"}:
        take_trade_parts.append(f"chart structure is {vision.get('quality')}")
    if execution.get("quality") == "GOOD":
        take_trade_parts.append("execution quality is clean")
    if options_reasons:
        take_trade_parts.append("options data confirms tradability")
    if probabilities.get("win_probability"):
        take_trade_parts.append(f"modeled win probability is {probabilities.get('win_probability', 0) * 100:.0f}%")
    if not take_trade_parts:
        take_trade_parts.append("the setup is still being validated against chart, technical, and options inputs")

    lines = [
        f"AI Reasoning: {trade_type} {direction} {ticker} classified as {decision} with composite score {final_score}/100.",
        f"Market regime: {regime.get('regime', 'UNKNOWN')} ({regime.get('confidence', 0)}% confidence).",
        f"Market phase: {market_phase.get('phase', 'UNKNOWN')} ({market_phase.get('confidence', 0)}% confidence); adaptive minimum score {adaptive_min_score or 'n/a'}.",
        f"MTF structure: {mtf.get('structure', 'UNKNOWN')} with {mtf.get('aligned_timeframes', 0)} aligned timeframes.",
        f"Execution quality: {execution.get('quality', 'UNKNOWN')} | Setup filter: {setup_quality.get('status', 'UNKNOWN')} | Chart structure: {vision.get('quality', 'UNKNOWN')}.",
        f"Weighted ensemble: {ensemble_score if ensemble_score is not None else 'n/a'} with components {component_scores}; rank {quality_rank or 'n/a'}; probabilistic tier {probabilistic_tier or 'n/a'}.",
        f"Probabilities: win {probabilities.get('win_probability', 0):.2f}, continuation {probabilities.get('trend_continuation_probability', 0):.2f}, reversal {probabilities.get('reversal_probability', 0):.2f}, trap {probabilities.get('trap_probability', 0):.2f}.",
        "Take-trade thesis: " + "; ".join(take_trade_parts) + ".",
    ]

    if tech_observations:
        lines.append("Ticker-adaptive technical read: " + "; ".join(tech_observations[:7]) + ".")

    if option_flow or option_contract:
        flow_summary = (
            f"flow {option_flow.get('bias', 'n/a')} {option_flow.get('score', 'n/a')}/100, "
            f"gamma {option_flow.get('dealer_gamma_state', 'n/a')}, squeeze {option_flow.get('gamma_squeeze', 'n/a')}"
        ) if option_flow else "flow n/a"
        contract_summary = (
            f"contract {option_contract.get('contract_symbol', 'n/a')} spread {option_contract.get('spread_pct', 'n/a')}%, "
            f"vol/OI {option_contract.get('volume', 'n/a')}/{option_contract.get('open_interest', 'n/a')}, "
            f"delta {option_contract.get('delta', 'n/a')}, DTE {option_contract.get('dte', 'n/a')}"
        ) if option_contract else "contract n/a"
        lines.append(
            f"Options analysis: adjustment {options_analysis.get('score_adjustment', 0):+.1f}; "
            f"{flow_summary}; {contract_summary}."
        )
        if options_reasons:
            lines.append("Options confirmation: " + "; ".join(options_reasons[:4]) + ".")
        if options_warnings:
            lines.append("Options cautions: " + "; ".join(options_warnings[:4]) + ".")

    if learning_stats:
        lines.append(
            "Historical learning: "
            f"win rate {learning_stats.get('win_rate', 0) * 100:.1f}% over {learning_stats.get('closed', 0)} closed alerts; "
            f"forecast accuracy {learning_stats.get('forecast_accuracy', 0) * 100:.1f}%; "
            f"confidence {learning_confidence.get('base_confidence', 0):.1f}% -> {learning_confidence.get('calibrated_confidence', 0):.1f}%; "
            f"priority bonus {learning_priority_bonus:+.1f}."
        )

    if context_memory:
        lines.append(
            "Phase 4 context memory: "
            f"{context_memory.get('status', 'BASELINE')} via {context_memory.get('key')}; "
            f"adjustment {context_memory.get('score_adjustment', 0):+.1f}."
        )

    if risk_plan:
        lines.append(
            "Phase 5 risk plan: "
            f"{risk_plan.get('action')} at {risk_plan.get('risk_multiplier', 0):.2f}x risk; "
            f"max risk ${risk_plan.get('max_risk_dollars', 0):.2f}; "
            f"size {risk_plan.get('position_size', 0)}."
        )

    if reasons:
        lines.append("Strengths: " + "; ".join(reasons[:6]) + ".")

    if warnings:
        lines.append("Warnings: " + "; ".join(warnings[:5]) + ".")

    if no_trade.get("score"):
        lines.append(f"No-trade score: {no_trade.get('score')}/100 from {'; '.join(no_trade.get('reasons') or [])}.")

    if reject_reasons:
        lines.append("Reject risks converted to penalties: " + "; ".join(reject_reasons[:4]) + ".")

    human_summary = _build_human_readable_summary(
        ticker=ticker,
        direction=direction,
        mtf=mtf,
        execution=execution,
        setup_quality=setup_quality,
        vision=vision,
        regime=regime,
        options_reasons=options_reasons,
        options_warnings=options_warnings,
        risk_plan=risk_plan,
        no_trade=no_trade,
    )

    return human_summary + "\n\nDetailed model diagnostics\n\n" + "\n".join(lines)


def should_send_reasoned_alert(report: Dict[str, Any], min_score=80) -> bool:
    report = report or {}

    if report.get("decision") == "REJECT":
        return False

    if report.get("final_score", 0) < min_score:
        return False

    return True
