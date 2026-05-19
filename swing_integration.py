import csv
import datetime as dt
import re
import time

from bot_utils import safe_float

from config import (
    ENABLE_SWING_ALERTS,
    LOG_FILE,
    SUCCESS_RATE_MIN_CALIBRATED_PROBABILITY,
    SUCCESS_RATE_MODE,
    SWING_ALERT_COOLDOWN_SEC,
    SWING_HOLD_DAYS_MAX,
)
from swing_scanner import score_swing_setup, format_swing_alert
from ai_reasoning_engine import build_reasoning_report
from execution_quality import GOOD as EXECUTION_GOOD, WARNING as EXECUTION_WARNING
from setup_filters import PASS, REJECT, WARNING
from outcome_tracker import track_outcome
from performance_learning import calibrate_confidence, priority_bonus, setup_structure_key
from options_engine import analyze_options_flow, option_to_dict, options_flow_to_dict, select_option_contract
from option_order_manager import (
    has_valid_option_contract_order_details,
    missing_option_contract_order_details,
    maybe_buy_recommended_option,
)
from alert_history import mark_alerted_today, was_alerted_today
from ml_sklearn_model import adjust_score_with_logistic, build_ml_feature_row

SWING_ALERT_CACHE = {}


def _option_contract_has_stale_fallback(option_contract):
    if not isinstance(option_contract, dict):
        option_contract = getattr(option_contract, "__dict__", {}) if option_contract else {}
    reason = str(option_contract.get("reason") or "").lower()
    return "stale" in reason and "fallback" in reason


def _success_rate_block_reason(setup, reasoning=None):
    if not SUCCESS_RATE_MODE:
        return ""
    setup = setup or {}
    reasoning = reasoning or setup.get("ai_reasoning") or {}
    risk_action = str(((reasoning.get("risk_plan") or {}).get("action")) or setup.get("risk_action") or "").upper()
    decision = str(reasoning.get("decision") or setup.get("decision") or setup.get("tier") or "").upper()
    quality_rank = str(reasoning.get("quality_rank") or setup.get("quality_rank") or "").upper()
    probabilities = reasoning.get("probabilities") or {}
    calibrated_probability = probabilities.get("win_probability")
    if calibrated_probability in (None, ""):
        calibrated_probability = setup.get("ml_probability")
    if calibrated_probability in (None, ""):
        calibrated_probability = setup.get("calibrated_confidence")
        try:
            calibrated_probability = float(calibrated_probability) / 100.0
        except Exception:
            calibrated_probability = None
    if risk_action == "WATCH_ONLY":
        return "SUCCESS_RATE_MODE blocked WATCH_ONLY risk plan"
    if decision == "NO_TRADE" or quality_rank == "NO_TRADE" or (reasoning.get("no_trade") or {}).get("is_no_trade"):
        return "SUCCESS_RATE_MODE blocked NO_TRADE setup"
    if _option_contract_has_stale_fallback(setup.get("option_contract")):
        return "SUCCESS_RATE_MODE blocked stale fallback option contract"
    try:
        if calibrated_probability is not None and float(calibrated_probability) < SUCCESS_RATE_MIN_CALIBRATED_PROBABILITY:
            return (
                "SUCCESS_RATE_MODE blocked low calibrated probability "
                f"{float(calibrated_probability):.2f} < {SUCCESS_RATE_MIN_CALIBRATED_PROBABILITY:.2f}"
            )
    except Exception:
        return "SUCCESS_RATE_MODE blocked unreadable calibrated probability"
    return ""


SWING_MIN_BENCHMARK_RR = 1.8
SWING_ALLOWED_DECISIONS = {"A+", "A"}
SWING_MIN_COMPOSITE_SCORE = 92
SWING_ALLOWED_REGIMES = {"TRENDING_BULL", "TRENDING_BEAR", "MIXED"}
SWING_ALLOWED_EXECUTION = {EXECUTION_GOOD, EXECUTION_WARNING}
SWING_ALLOWED_SETUP_FILTERS = {PASS, WARNING, REJECT}
SWING_ALLOWED_CHART_STRUCTURES = {"ELITE", "GOOD"}
SWING_ALLOWED_MTF_STRUCTURES = {"STRONG_ALIGNMENT", "GOOD_ALIGNMENT"}
SWING_MIXED_REGIME_ELITE_SCORE = 100
SWING_MIXED_MTF_ELITE_SCORE = 95
SWING_MIXED_MTF_MIN_ADX = 22
SWING_MIXED_MTF_MIN_REL_VOLUME = 1.8
SWING_MIXED_MTF_MIN_BODY_PCT = 0.6
SWING_OPTION_MIN_DTE = 7
SWING_OPTION_MAX_DTE = 14


SWING_NON_BLOCKING_AI_REJECT_REASONS = {"Setup failed elite quality filters"}


def _blocking_ai_reject_reasons(reasoning):
    """Return AI reject reasons that should still block benchmark-quality swings."""
    raw_reasons = reasoning.get("reject_reasons") or []
    return [
        str(reason)
        for reason in raw_reasons
        if str(reason) not in SWING_NON_BLOCKING_AI_REJECT_REASONS
    ]


def _regime_allowed_for_strict_mode(regime):
    """Return True when regime is allowed by strict sniper mode."""
    return regime in SWING_ALLOWED_REGIMES


def _truthy_benchmark_flag(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "confirmed", "held", "pass"}
    return bool(value)


def _body_pct_fraction(value):
    body_pct = safe_float(value)
    if body_pct > 1:
        body_pct /= 100
    return body_pct


def _swing_price_action_confirmed(setup, tech):
    setup = setup or {}
    tech = tech or {}
    reasons_text = " ".join(str(reason).lower() for reason in setup.get("reasons") or [])

    body_pct = max(
        _body_pct_fraction(tech.get("candle_body_pct")),
        _body_pct_fraction(tech.get("body_pct")),
        _body_pct_fraction(setup.get("candle_body_pct")),
        _body_pct_fraction(setup.get("body_pct")),
    )
    strong_body = body_pct >= SWING_MIXED_MTF_MIN_BODY_PCT

    breakout_confirmed = any(
        _truthy_benchmark_flag(value)
        for value in (
            tech.get("breakout_confirmed"),
            tech.get("breakout"),
            setup.get("breakout_confirmed"),
            setup.get("breakout"),
        )
    ) or "breakout" in reasons_text or "breakdown" in reasons_text

    retest_confirmed = any(
        _truthy_benchmark_flag(value)
        for value in (
            tech.get("retest_confirmed"),
            tech.get("retest_hold"),
            setup.get("retest_confirmed"),
            setup.get("retest_hold"),
        )
    ) or "retest" in reasons_text

    return strong_body or (breakout_confirmed and retest_confirmed)


def _allows_mixed_mtf_swing(setup, reasoning, tech, regime_aligned):
    """Allow elite A+ swing setups through a mixed-MTF gate when momentum confirms."""
    setup = setup or {}
    reasoning = reasoning or {}
    tech = tech or {}

    composite_score = safe_float(reasoning.get("final_score") or setup.get("score"))
    decision = reasoning.get("decision") or setup.get("decision")
    adx = safe_float(tech.get("adx") or setup.get("adx"))
    rel_volume = safe_float(
        tech.get("rel_volume")
        or tech.get("relative_volume")
        or setup.get("rel_volume")
        or setup.get("relative_volume")
    )

    return (
        composite_score >= SWING_MIXED_MTF_ELITE_SCORE
        and decision == "A+"
        and regime_aligned
        and adx > SWING_MIXED_MTF_MIN_ADX
        and rel_volume > SWING_MIXED_MTF_MIN_REL_VOLUME
        and _swing_price_action_confirmed(setup, tech)
    )


def swing_benchmark_reject_reasons(setup, reasoning, tech=None):
    """Return human-readable reasons why a swing setup misses the benchmark."""
    setup = setup or {}
    reasoning = reasoning or {}
    reasons = []

    direction = setup.get("direction")
    if direction not in {"CALL", "PUT"}:
        reasons.append("direction is not CALL or PUT")

    decision = reasoning.get("decision")
    if decision not in SWING_ALLOWED_DECISIONS:
        allowed = "/".join(sorted(SWING_ALLOWED_DECISIONS))
        reasons.append(f"decision {decision or 'missing'} is not {allowed}")

    composite_score = safe_float(reasoning.get("final_score") or setup.get("score"))
    if composite_score < SWING_MIN_COMPOSITE_SCORE:
        reasons.append(f"score {composite_score:g} is below {SWING_MIN_COMPOSITE_SCORE}")

    risk_reward = safe_float(setup.get("risk_reward"))
    if risk_reward < SWING_MIN_BENCHMARK_RR:
        reasons.append(f"risk/reward {risk_reward:g}R is below {SWING_MIN_BENCHMARK_RR:g}R")

    ai_reject_reasons = _blocking_ai_reject_reasons(reasoning)
    if ai_reject_reasons:
        reasons.append("AI reject risks: " + "; ".join(ai_reject_reasons))

    regime = (reasoning.get("regime") or {}).get("regime")
    if not _regime_allowed_for_strict_mode(regime):
        allowed = "/".join(sorted(SWING_ALLOWED_REGIMES))
        reasons.append(f"regime {regime or 'missing'} is not {allowed}")

    regime_aligned = _regime_allowed_for_strict_mode(regime)

    mtf_structure = (reasoning.get("mtf") or {}).get("structure")
    if mtf_structure not in SWING_ALLOWED_MTF_STRUCTURES and not (
        mtf_structure == "MIXED_ALIGNMENT"
        and _allows_mixed_mtf_swing(setup, reasoning, tech, regime_aligned)
    ):
        allowed = "/".join(sorted(SWING_ALLOWED_MTF_STRUCTURES))
        reasons.append(f"MTF {mtf_structure or 'missing'} is not {allowed}")

    execution = (reasoning.get("execution") or {}).get("quality")
    if execution not in SWING_ALLOWED_EXECUTION:
        allowed = "/".join(sorted(SWING_ALLOWED_EXECUTION))
        reasons.append(f"execution {execution or 'missing'} is not {allowed}")

    setup_filter = (reasoning.get("setup_quality") or {}).get("status")
    if setup_filter not in SWING_ALLOWED_SETUP_FILTERS:
        allowed = "/".join(sorted(SWING_ALLOWED_SETUP_FILTERS))
        reasons.append(f"setup filter {setup_filter or 'missing'} is not {allowed}")

    chart_structure = (reasoning.get("vision") or {}).get("quality")
    if chart_structure not in SWING_ALLOWED_CHART_STRUCTURES:
        allowed = "/".join(sorted(SWING_ALLOWED_CHART_STRUCTURES))
        reasons.append(f"chart structure {chart_structure or 'missing'} is not {allowed}")

    return reasons


def meets_swing_benchmark(setup, reasoning, tech=None):
    """Return True for high-quality swing alerts that pass the relaxed benchmark."""
    return not swing_benchmark_reject_reasons(setup, reasoning, tech)


def _hold_days_to_horizon_minutes(hold_days, default_days=SWING_HOLD_DAYS_MAX):
    """Convert a swing hold-days value into an outcome-tracking horizon.

    Swing alerts display hold windows such as ``"2-10"`` days. For outcome
    tracking, use the far end of that range so the trade has the full advertised
    holding window to reach its stop or target.
    """
    if hold_days is None or hold_days == "":
        days = default_days
    elif isinstance(hold_days, (int, float)):
        days = hold_days
    else:
        day_values = re.findall(r"\d+(?:\.\d+)?", str(hold_days))
        days = float(day_values[-1]) if day_values else default_days

    if days <= 0:
        days = default_days

    return int(days * 24 * 60)


def log_swing_alert(ticker, setup, tech):
    setup = setup or {}
    tech = tech or {}

    fields = [
        "timestamp", "ticker", "alert_type", "direction", "entry_mode", "score",
        "ml_probability", "entry", "stop", "target", "risk_reward", "hold_days",
        "price", "dma20", "dma50", "dma200", "atr14", "setup_key", "learning_key", "learning_win_rate", "forecast_accuracy", "priority_bonus", "reasons", "options_flow_bias", "options_flow_score", "options_flow_gamma_squeeze",
    ]

    reasoning = setup.get("ai_reasoning") or {}
    learning_context = reasoning.get("learning_context") or {}
    learning_confidence = reasoning.get("learning_confidence") or {}
    learning_stats = learning_confidence.get("learning_stats") or {}
    setup_key = learning_context.get("setup_key") or setup_structure_key({"alert_type": "SWING", "entry_mode": "SWING", "direction": setup.get("direction")})

    row = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ticker": ticker,
        "alert_type": "SWING",
        "direction": setup.get("direction"),
        "entry_mode": "SWING",
        "score": setup.get("score"),
        "ml_probability": setup.get("ml_probability"),
        "entry": setup.get("entry"),
        "stop": setup.get("stop"),
        "target": setup.get("target"),
        "risk_reward": setup.get("risk_reward"),
        "hold_days": setup.get("hold_days"),
        "price": tech.get("price"),
        "dma20": tech.get("dma20"),
        "dma50": tech.get("dma50"),
        "dma200": tech.get("dma200"),
        "atr14": tech.get("atr14"),
        "setup_key": setup_key,
        "learning_key": learning_confidence.get("learning_key"),
        "learning_win_rate": learning_stats.get("win_rate"),
        "forecast_accuracy": learning_stats.get("forecast_accuracy"),
        "priority_bonus": reasoning.get("priority_bonus"),
        "reasons": ", ".join(setup.get("reasons", [])),
        "options_flow_bias": (setup.get("options_flow") or {}).get("bias"),
        "options_flow_score": (setup.get("options_flow") or {}).get("score"),
        "options_flow_gamma_squeeze": (setup.get("options_flow") or {}).get("gamma_squeeze"),
    }

    try:
        file_exists = False
        try:
            with open(LOG_FILE, "r", encoding="utf-8"):
                file_exists = True
        except FileNotFoundError:
            pass

        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        print(f"{ticker}: swing log error: {e}")


def swing_ranking_score(setup):
    """Return a scan-comparable rank for high-quality swing candidates."""
    setup = setup or {}
    reasoning = setup.get("ai_reasoning") or {}
    score = safe_float(setup.get("score") or reasoning.get("final_score"))
    risk_reward = safe_float(setup.get("risk_reward"))
    confidence = safe_float(setup.get("calibrated_confidence") or setup.get("ml_probability"))
    priority = safe_float(setup.get("historical_priority_bonus") or reasoning.get("priority_bonus"))

    ranking = score + (risk_reward * 10) + confidence + priority
    if setup.get("decision") == "A+" or setup.get("tier") == "A+":
        ranking += 20
    elif setup.get("decision") == "A" or setup.get("tier") == "A":
        ranking += 10

    mtf_structure = (reasoning.get("mtf") or {}).get("structure")
    if mtf_structure == "STRONG_ALIGNMENT":
        ranking += 15
    elif mtf_structure == "GOOD_ALIGNMENT":
        ranking += 10

    chart_structure = (reasoning.get("vision") or {}).get("quality")
    if chart_structure == "ELITE":
        ranking += 10
    elif chart_structure == "GOOD":
        ranking += 5

    return round(ranking, 2)


def send_prepared_swing_candidate(bot, ticker, setup, tech, alert_time=None):
    """Send, log, and track an already-ranked swing candidate."""
    if was_alerted_today(ticker):
        print(f"{ticker}: swing skipped, alert already sent today")
        return False

    setup = setup or {}
    tech = tech or {}
    alert_time = alert_time or time.time()

    telegram_sent = False
    option_contract = setup.get("option_contract") or {}
    has_orderable_option = has_valid_option_contract_order_details(option_contract)
    if not has_orderable_option:
        missing_option_details = missing_option_contract_order_details(option_contract)
        option_status = option_contract.get("status") if isinstance(option_contract, dict) else None
        option_reason = option_contract.get("reason") if isinstance(option_contract, dict) else None
        detail_text = ", ".join(missing_option_details)
        reason_text = (
            f"; status={option_status or 'missing'}; reason={option_reason}"
            if option_reason or option_status
            else ""
        )
        print(
            f"{ticker}: swing alert continuing without orderable option contract "
            f"({detail_text}{reason_text})"
        )

    try:
        message = format_swing_alert(ticker, setup)
        telegram_sent = bool(bot.send_telegram_msg(message))
        if telegram_sent:
            if has_orderable_option:
                maybe_buy_recommended_option(
                    ticker=ticker,
                    direction=setup.get("direction"),
                    option_contract=option_contract,
                    telegram_sender=bot.send_telegram_msg,
                )
            SWING_ALERT_CACHE[ticker] = alert_time
            mark_alerted_today(ticker)
        else:
            print(f"{ticker}: swing telegram send failed; alert not counted as sent")
    except Exception as e:
        print(f"{ticker}: swing telegram error: {e}")

    if not telegram_sent:
        return False

    log_swing_alert(ticker, setup, tech)

    try:
        alert_time_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        reasoning = setup.get("ai_reasoning") or {}
        learning_context = reasoning.get("learning_context") or {}
        track_outcome(
            ticker=ticker,
            direction=setup.get("direction"),
            entry=float(setup.get("entry")),
            stop=float(setup.get("stop")),
            target=float(setup.get("target")),
            alert_time_iso=alert_time_iso,
            alert_type="SWING",
            entry_mode="SWING",
            horizon_minutes=_hold_days_to_horizon_minutes(setup.get("hold_days")),
            setup_context={
                "setup_key": learning_context.get("setup_key"),
                "market_regime": (reasoning.get("regime") or {}).get("regime"),
                "mtf_structure": (reasoning.get("mtf") or {}).get("structure"),
                "chart_structure": (reasoning.get("vision") or {}).get("quality"),
                "ai_confidence": setup.get("score"),
                "calibrated_confidence": setup.get("calibrated_confidence"),
                "score": setup.get("score"),
                "ml_probability": setup.get("ml_probability"),
                "win_probability": (reasoning.get("probabilities") or {}).get("win_probability"),
                "tech": tech,
                "setup": setup,
                "reasoning": reasoning,
                "option_contract": setup.get("option_contract"),
                "options_flow": setup.get("options_flow"),
                "market_phase": (reasoning.get("market_phase") or {}).get("phase"),
                "atr_extension": tech.get("atr_extension") or tech.get("breakout_distance_atr"),
                "wick_ratio": tech.get("wick_ratio"),
                "candle_body_pct": tech.get("candle_body_pct") or tech.get("body_pct"),
                "distance_from_vwap": tech.get("distance_from_vwap"),
                "distance_from_ema21": tech.get("distance_from_ema21") or tech.get("price_vs_ema21_pct"),
                "rel_volume": tech.get("rel_volume"),
                "sector_relative_strength": tech.get("sector_relative_strength"),
                "deep_ai_approval": reasoning.get("decision") or setup.get("tier"),
                "deep_ai_rejection_reason": ", ".join(reasoning.get("reject_reasons") or []),
            },
        )
    except Exception as e:
        print(f"{ticker}: swing outcome tracking skipped: {e}")

    return True


def process_swing_candidate(bot, ticker, tech, send_alert=True):
    if not ENABLE_SWING_ALERTS:
        return None

    if was_alerted_today(ticker):
        print(f"{ticker}: swing skipped, alert already sent today")
        return None

    tech = tech or {}

    now = time.time()
    last_alert = SWING_ALERT_CACHE.get(ticker)

    if last_alert and (now - last_alert) < SWING_ALERT_COOLDOWN_SEC:
        remaining = int((SWING_ALERT_COOLDOWN_SEC - (now - last_alert)) / 60)
        print(f"{ticker}: swing cooldown active ({remaining}m remaining)")
        return None

    try:
        setup = score_swing_setup(tech)
    except Exception as e:
        print(f"{ticker}: swing setup scoring error: {e}")
        return None

    if setup is None:
        return None

    if not isinstance(setup, dict):
        print(f"{ticker}: invalid swing setup object")

        return None

    try:
        reasoning = build_reasoning_report(
            ticker=ticker,
            setup=setup,
            tech=tech,
            bot=bot,
            trade_type="SWING",
        ) or {}

        if not isinstance(reasoning, dict):
            reasoning = {}

        setup["ai_reasoning"] = reasoning
        setup["score"] = reasoning.get("final_score", setup.get("score", 0))
        setup["decision"] = reasoning.get("decision", setup.get("tier", "WATCH"))

        benchmark_reject_reasons = swing_benchmark_reject_reasons(setup, reasoning, tech)
        if benchmark_reject_reasons:
            reason_text = "; ".join(benchmark_reject_reasons)
            print(
                f"{ticker}: swing benchmark rejected "
                f"({setup.get('direction')} {setup.get('decision')} score {setup.get('score')}): "
                f"{reason_text}"
            )
            return None
        learning_context = reasoning.get("learning_context") or {"alert_type": "SWING", "entry_mode": "SWING", "direction": setup.get("direction")}
        confidence_learning = calibrate_confidence(setup.get("score", 0), learning_context)
        setup["calibrated_confidence"] = confidence_learning.get("calibrated_confidence")
        setup["confidence_adjustment"] = confidence_learning.get("confidence_adjustment")
        setup["historical_priority_bonus"] = priority_bonus(learning_context)

    except Exception as e:
        print(f"{ticker}: reasoning engine error: {e}")
        setup["ai_reasoning"] = {}

    try:
        ml_row = build_ml_feature_row(tech=tech, setup=setup, ai=setup, intraday_info={})
        adjusted, prob, model_info = adjust_score_with_logistic(
            ml_row,
            setup.get("score", 0),
        )

        setup["score"] = adjusted
        setup["ml_probability"] = prob

        setup["ml_model_info"] = model_info

    except Exception as e:
        print(f"{ticker}: swing ML skipped: {e}")

    try:
        reasoning = setup.get("ai_reasoning") or {}
        learning_context = reasoning.get("learning_context") or {"alert_type": "SWING", "entry_mode": "SWING", "direction": setup.get("direction")}
        setup["score"] = round(max(0, min(100, float(setup.get("score", 0) or 0) + priority_bonus(learning_context))), 2)
    except Exception as e:
        print(f"{ticker}: swing historical prioritization skipped: {e}")

    try:
        flow_report = analyze_options_flow(ticker, setup.get("direction"))
        setup["options_flow"] = options_flow_to_dict(flow_report)
        if flow_report.status == "OK":
            if flow_report.bias == "BULLISH" and setup.get("direction") == "CALL":
                setup["score"] = round(min(100, float(setup.get("score", 0) or 0) + flow_report.score * 0.08), 2)
            elif flow_report.bias == "BEARISH" and setup.get("direction") == "PUT":
                setup["score"] = round(min(100, float(setup.get("score", 0) or 0) + flow_report.score * 0.08), 2)
            elif flow_report.bias in {"BULLISH", "BEARISH"}:
                setup.setdefault("reasons", []).append(f"Options flow conflict: {flow_report.bias}")

        option_contract = select_option_contract(
            ticker,
            {"signal": setup.get("direction"), "price": setup.get("price") or setup.get("entry")},
            min_dte=SWING_OPTION_MIN_DTE,
            max_dte=SWING_OPTION_MAX_DTE,
            allow_default_fallback=True,
        )
        setup["option_contract"] = option_to_dict(option_contract)
        missing_option_details = missing_option_contract_order_details(setup["option_contract"])
        if missing_option_details:
            option_status = setup["option_contract"].get("status")
            option_reason = setup["option_contract"].get("reason")
            detail_text = ", ".join(missing_option_details)
            reason_text = (
                f"; status={option_status or 'missing'}; reason={option_reason}"
                if option_reason or option_status
                else ""
            )
            print(
                f"{ticker}: swing continuing without orderable option contract "
                f"({detail_text}{reason_text})"
            )
        else:
            option_score_bonus = min(5, (option_contract.recommendation_score or 0) * 0.04)
            setup["score"] = round(
                min(100, float(setup.get("score", 0) or 0) + option_score_bonus),
                2,
            )
    except Exception as e:
        print(f"{ticker}: swing option contract selection skipped: {e}")
        setup["option_contract"] = {
            "status": "SKIP",
            "reason": f"Option contract selection failed: {e}",
        }

    try:
        reasoning_input = dict(setup)
        previous_reasoning = setup.get("ai_reasoning") or {}
        if previous_reasoning.get("base_score") is not None:
            reasoning_input["score"] = previous_reasoning.get("base_score")
        refreshed_reasoning = build_reasoning_report(
            ticker=ticker,
            setup=reasoning_input,
            tech=tech,
            bot=bot,
            trade_type="SWING",
        ) or {}
        if isinstance(refreshed_reasoning, dict):
            setup["ai_reasoning"] = refreshed_reasoning
            setup["score"] = refreshed_reasoning.get("final_score", setup.get("score", 0))
            setup["decision"] = refreshed_reasoning.get("decision", setup.get("decision", setup.get("tier", "WATCH")))
    except Exception as e:
        print(f"{ticker}: options-aware swing reasoning refresh skipped: {e}")

    success_block = _success_rate_block_reason(setup, setup.get("ai_reasoning"))
    if success_block:
        print(f"{ticker}: swing rejected - {success_block}")
        return None

    setup["ranking_score"] = swing_ranking_score(setup)

    if not send_alert:
        return setup

    if not send_prepared_swing_candidate(bot, ticker, setup, tech, alert_time=now):
        return None

    return setup
