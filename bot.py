from config import *
from openai import OpenAI

import requests

from telegram_formatting import html_payload
import asyncio
import datetime as dt
import csv
import base64
from typing import Dict, Any

from bot_technical import StockTechnicalBase
from bot_utils import fmt_price, extract_gpt_json, normalize_ai_response
from alert_formatting import format_predicted_price_move, format_recommended_option_contract
from openai_models import chat_completion_options
from outcome_tracker import track_outcome
from chart_capture import capture_chart
from intraday_confirm import intraday_confirmation
from ai_scoring import ai_score_setup
from ai_reasoning_engine import build_reasoning_report
from performance_learning import calibrate_confidence, priority_bonus, setup_structure_key
from market_phase import detect_market_phase
from ensemble_confidence import dynamic_min_score, setup_decay_score
from daily_report_engine import send_daily_learning_report
from options_engine import analyze_options_flow, format_options_flow, option_to_dict, options_flow_to_dict, select_option_contract
from option_order_manager import (
    OPTION_PRICE_CHECK_INTERVAL_SEC,
    has_valid_option_contract_order_details,
    manage_open_option_positions,
    missing_option_contract_order_details,
    maybe_buy_recommended_option,
)
from alert_history import mark_alerted_today, was_alerted_today


ai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def log_alert(row: Dict[str, Any]):
    file_exists = False
    try:
        with open(LOG_FILE, "r"):
            file_exists = True
    except FileNotFoundError:
        pass

    fields = [
        "timestamp", "ticker", "direction", "entry_mode", "score", "rule_score", "ranking_score",
        "ai_verdict", "ai_confidence", "calibrated_confidence", "confidence_adjustment", "setup_quality", "entry_timing",
        "entry", "stop", "target", "risk_reward",
        "retest_confirmed", "late_breakout_risk", "ai_reason",
        "price", "latest_price_time", "latest_regular_time", "intraday_data_source",
        "intraday_data_delay_sec", "realtime_overlay_active", "vwap", "ema9", "ema21", "ema50",
        "dma20", "dma50", "dma200", "atr14",
        "trend_5m", "trend_15m", "orb_high", "orb_low",
        "premarket_high", "premarket_low", "prev_high", "prev_low",
        "current_volume", "avg_20_volume",
        "intraday_confirmations", "intraday_required", "intraday_reason",
        "market_bias", "market_details", "market_regime", "market_phase", "ensemble_score", "quality_rank", "win_probability", "trap_probability", "no_trade_score", "risk_action", "risk_multiplier", "max_risk_dollars", "phase4_context_key", "phase4_context_adjustment", "mtf_structure", "chart_structure", "setup_key", "learning_key", "learning_win_rate", "forecast_accuracy", "priority_bonus", "reasons",
        "atr_extension", "wick_ratio", "candle_body_pct", "distance_from_vwap", "distance_from_ema21", "rel_volume", "spread_pct", "option_volume", "open_interest", "sector_relative_strength", "deep_ai_approval", "deep_ai_rejection_reason",
        "options_flow_bias", "options_flow_score", "options_flow_gamma_squeeze",
    ]

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


class StockTechnicalAIBot(StockTechnicalBase):
    def send_telegram_msg(self, msg):
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            print("Telegram not configured; alert was not sent")
            print(msg)
            return False

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        formatted_payload = html_payload(TELEGRAM_CHAT_ID, msg)
        plain_payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}

        try:
            response = requests.post(url, data=formatted_payload, timeout=10)
            if response.ok:
                return True

            print(f"Telegram formatted send failed ({response.status_code}): {response.text}")
            fallback_response = requests.post(url, data=plain_payload, timeout=10)
            if fallback_response.ok:
                print("Telegram alert sent without formatting")
                return True

            print(
                "Telegram plain-text send failed "
                f"({fallback_response.status_code}): {fallback_response.text}"
            )
            return False
        except requests.RequestException as e:
            print(f"Telegram error: {e}")
            return False

    def encode_image(self, path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def fallback_atr_trade_plan(self, setup, tech):
        entry = tech["price"]
        atr = tech.get("atr14")
        if not atr:
            return entry, None, None, 0

        if setup["direction"] == "CALL":
            stop = entry - atr * ATR_STOP_MULTIPLIER
            target = entry + atr * ATR_TARGET_MULTIPLIER
            risk = entry - stop
            reward = target - entry
        else:
            stop = entry + atr * ATR_STOP_MULTIPLIER
            target = entry - atr * ATR_TARGET_MULTIPLIER
            risk = stop - entry
            reward = entry - target

        rr = reward / risk if risk > 0 else 0
        return entry, stop, target, rr

    def apply_ai_scoring(self, ticker, tech, setup):
        """Replace rule score with AI score while preserving the original rule score."""
        setup = dict(setup)
        rule_score = int(setup.get("score", 0) or 0)
        setup["rule_score"] = rule_score

        try:
            ai_score = int(ai_score_setup(ticker, tech, setup) or rule_score)
            ai_score = max(0, min(ai_score, 100))
        except Exception as e:
            print(f"{ticker}: AI scoring failed, keeping rule score: {e}")
            ai_score = rule_score

        setup["score"] = ai_score
        setup.setdefault("reasons", []).append(f"AI score override: {rule_score} -> {ai_score}")
        return setup

    def detect_entry_mode(self, setup, tech, intraday_info):
        direction = setup["direction"]
        reasons_text = " ".join(setup.get("reasons", [])).lower()
        confirmations = int(intraday_info.get("confirmations", 0) or 0)
        rel_vol = float(intraday_info.get("rel_volume_5m", 0) or 0)
        trigger_dist = float(intraday_info.get("trigger_distance_pct", 0) or 0)

        if setup.get("retest_confirmed"):
            return "RETEST", "Retest confirmed near key level"

        if "breakout" in reasons_text or "breakdown" in reasons_text:
            if rel_vol >= 1.5 and confirmations >= 3 and trigger_dist <= 1.25:
                return "BREAKOUT", "Breakout with volume and intraday confirmation"

        if confirmations >= 3 and 0.75 <= trigger_dist <= 2.0:
            return "MOMENTUM", "Continuation/momentum entry within allowed extension"

        if direction == "CALL" and tech.get("ema21") and tech["price"] >= tech["ema21"]:
            return "PULLBACK", "Bullish pullback/reclaim near EMA21/VWAP zone"

        if direction == "PUT" and tech.get("ema21") and tech["price"] <= tech["ema21"]:
            return "PULLBACK", "Bearish pullback/rejection near EMA21/VWAP zone"

        return "STANDARD", "General confirmed setup"

    def ai_fallback_decision(self, setup, tech, entry_mode):
        entry, stop, target, rr = self.fallback_atr_trade_plan(setup, tech)
        score = int(setup.get("score", 0) or 0)
        verdict = "BUY" if score >= MIN_CALL_SCORE and rr >= MIN_RISK_REWARD else "WAIT"
        return {
            "verdict": verdict,
            "confidence": min(max(score, 0), 95),
            "entry": entry,
            "stop": stop,
            "target": target,
            "risk_reward": rr,
            "setup_quality": "A" if score >= 85 else "B",
            "entry_timing": "EARLY" if entry_mode in {"BREAKOUT", "MOMENTUM"} else "IDEAL",
            "retest_confirmed": bool(setup.get("retest_confirmed")),
            "late_breakout_risk": bool(setup.get("late_breakout_risk")),
            "reason": f"ATR fallback decision using {entry_mode} mode.",
        }

    def ask_ai_decision(self, ticker, setup, tech, intraday_info, entry_mode, mode_reason):
        market = self.get_market_bias()
        fallback_entry, fallback_stop, fallback_target, fallback_rr = self.fallback_atr_trade_plan(setup, tech)

        if not ai_client:
            return self.ai_fallback_decision(setup, tech, entry_mode)

        prompt = f"""
Analyze this intraday stock setup and return only JSON.

Ticker: {ticker}
Direction: {setup['direction']}
Entry Mode: {entry_mode}
Entry Mode Reason: {mode_reason}
AI Score: {setup['score']}
Original Rule Score: {setup.get('rule_score')}
Reasons: {', '.join(setup.get('reasons', []))}

Price: {tech['price']}
VWAP: {tech['vwap']}
EMA9/21/50: {tech['ema9']} / {tech['ema21']} / {tech['ema50']}
DMA20/50/200: {tech['dma20']} / {tech['dma50']} / {tech['dma200']}
ATR14: {tech['atr14']}
5m Trend: {tech['trend_5m']}
15m Trend: {tech['trend_15m']}
ORB High/Low: {tech['orb_high']} / {tech['orb_low']}
Premarket High/Low: {tech['premarket_high']} / {tech['premarket_low']}
Previous Day High/Low: {tech['prev_high']} / {tech['prev_low']}
Recent High/Low: {tech['recent_high']} / {tech['recent_low']}
Volume: {tech['current_volume']} / Avg20 {tech['avg_20_volume']}
Intraday Confirmation: {intraday_info}
Market Bias: {market}

ATR Plan: entry={fallback_entry}, stop={fallback_stop}, target={fallback_target}, rr={fallback_rr}

Rules:
- BREAKOUT: allow without perfect retest if volume, VWAP, and intraday confirmation are strong.
- RETEST: prefer best quality; validate reclaim/rejection and defined stop.
- MOMENTUM: allow continuation up to 2% extension only if trend and volume are strong.
- PULLBACK: allow starter only if price reclaims/holds EMA21 or VWAP and risk is defined.
- Reject chop, failed moves, late extensions, and poor risk/reward.
- Minimum acceptable R/R is {MIN_RISK_REWARD}:1.

Return ONLY valid JSON:
{{
  "verdict": "BUY" or "WAIT",
  "confidence": number from 0 to 100,
  "entry": numeric entry price or null,
  "stop": numeric stop price or null,
  "target": numeric target price or null,
  "risk_reward": numeric risk reward ratio,
  "setup_quality": "A+" or "A" or "B" or "LOW",
  "entry_timing": "EARLY" or "IDEAL" or "LATE" or "CHOP",
  "retest_confirmed": true or false,
  "late_breakout_risk": true or false,
  "reason": "2-3 sentence explanation including entry mode, price action, invalidation, and target logic."
}}
"""

        try:
            r = ai_client.chat.completions.create(
                **chat_completion_options(setup=setup, temperature=0.1),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an intraday options scalping risk manager. Approve valid A/B+ setups "
                            "when entry mode, volume, VWAP/EMA structure, and R/R are acceptable. "
                            "Do not over-reject clean breakout or momentum setups just because retest is imperfect."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            return normalize_ai_response(extract_gpt_json(r.choices[0].message.content or ""))
        except Exception as e:
            fallback = self.ai_fallback_decision(setup, tech, entry_mode)
            fallback["reason"] = f"OpenAI error: {e}; used ATR fallback for {entry_mode} mode."
            return fallback

    def ask_ai_with_chart(self, ticker, setup, tech, intraday_info, entry_mode, mode_reason, image_path):
        if not ai_client:
            return self.ai_fallback_decision(setup, tech, entry_mode)

        try:
            base64_image = self.encode_image(image_path)
            prompt = f"""
Validate the chart image plus data for this intraday options setup.
Ticker: {ticker}
Direction: {setup['direction']}
Entry Mode: {entry_mode}
AI Score: {setup['score']}
Rule Score: {setup.get('rule_score')}
Price: {tech['price']}
VWAP: {tech['vwap']}
EMA9/21/50: {tech['ema9']} / {tech['ema21']} / {tech['ema50']}
ATR14: {tech['atr14']}
Intraday Confirmation: {intraday_info}
Return ONLY valid JSON with verdict, confidence, entry, stop, target, risk_reward, setup_quality, entry_timing, retest_confirmed, late_breakout_risk, reason.
"""
            response = ai_client.chat.completions.create(
                **chat_completion_options(setup=setup, temperature=0.1),
                messages=[
                    {"role": "system", "content": "Use the chart to confirm structure. Reject chop, fakeouts, and late extensions."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                        ],
                    },
                ],
            )
            return normalize_ai_response(extract_gpt_json(response.choices[0].message.content or ""))
        except Exception as e:
            print(f"{ticker}: vision AI error: {e}")
            return self.ask_ai_decision(ticker, setup, tech, intraday_info, entry_mode, mode_reason)

    def ai_passes_gate(self, ai, setup, intraday_info, entry_mode):
        score = int(setup.get("score", 0) or 0)
        confirmations = int(intraday_info.get("confirmations", 0) or 0)
        rr = float(ai.get("risk_reward", 0) or 0)
        confidence = int(ai.get("confidence", 0) or 0)
        timing = ai.get("entry_timing")

        if rr < MIN_RISK_REWARD:
            return False, f"RR too low {rr}"
        if timing in ["LATE", "CHOP"]:
            return False, f"bad timing {timing}"
        if bool(ai.get("late_breakout_risk")) and entry_mode not in {"RETEST", "PULLBACK"}:
            return False, "AI sees late breakout risk"
        high_quality_score = MIN_SCORE
        required_confirmations = 3
        if bool(setup.get("early_session_setup")) and EARLY_SESSION_GRACE_ENABLED:
            high_quality_score = max(0, MIN_SCORE - EARLY_SESSION_MIN_SCORE_BUFFER)
            required_confirmations = min(required_confirmations, EARLY_SESSION_MIN_CONFIRMATIONS)

        high_quality_retest = (
            int(setup.get("rule_score", setup.get("score", 0)) or 0) >= MIN_SCORE
            and entry_mode == "RETEST"
            and bool(setup.get("retest_confirmed") or ai.get("retest_confirmed") or intraday_info.get("approved"))
        )
        confidence_floor = HIGH_QUALITY_RETEST_AI_CONFIDENCE if high_quality_retest else MIN_AI_CONFIDENCE
        if ai.get("verdict") == "BUY" and confidence >= confidence_floor:
            if confidence_floor < MIN_AI_CONFIDENCE:
                return True, f"AI approved by high-quality retest confidence floor {confidence_floor}"
            return True, "AI approved"

        if score >= high_quality_score and confirmations >= required_confirmations and entry_mode in {"BREAKOUT", "RETEST", "MOMENTUM"} and rr >= MIN_RISK_REWARD:
            reason = "early-session high-quality intraday setup with confirmation" if high_quality_score < MIN_SCORE else "high-quality intraday setup with confirmation"
            return True, f"override: {reason}"
        return False, ai.get("reason", "AI did not approve")

    async def build_candidate(self, ticker):
        if was_alerted_today(ticker):
            print(f"{ticker}: skipped, alert already sent today")
            return None

        tech = self.get_technical_context(ticker)
        if not tech:
            return None

        call = self.apply_ai_scoring(ticker, tech, self.score_call_setup(tech))
        put = self.apply_ai_scoring(ticker, tech, self.score_put_setup(tech))
        best = call if call["score"] >= put["score"] else put
        early_session_setup = bool(tech.get("early_session_setup")) and EARLY_SESSION_GRACE_ENABLED
        best["early_session_setup"] = early_session_setup
        min_score = MIN_CALL_SCORE if best["direction"] == "CALL" else MIN_PUT_SCORE
        if early_session_setup:
            min_score = max(0, min_score - EARLY_SESSION_MIN_SCORE_BUFFER)
            best.setdefault("reasons", []).append(
                f"early-session grace active: candidate score floor reduced by {EARLY_SESSION_MIN_SCORE_BUFFER}"
            )
        elif int(best.get("rule_score", 0) or 0) >= MIN_SCORE:
            min_score = min(min_score, HIGH_QUALITY_RETEST_AI_CONFIDENCE)
            best.setdefault("reasons", []).append(
                f"elite rule score prefilter: AI score floor reduced to {min_score} pending intraday confirmation"
            )

        print(
            f"{ticker}: price={fmt_price(tech['price'])}, "
            f"CALL_AI={call['score']} (rule={call.get('rule_score')}), "
            f"PUT_AI={put['score']} (rule={put.get('rule_score')}), best={best['direction']}"
        )

        market_snapshot = self.get_market_bias()
        phase_snapshot = detect_market_phase(tech, best, market_snapshot)
        best["market_phase"] = phase_snapshot
        adaptive_prefilter = dynamic_min_score((market_snapshot or {}).get("regime"), phase_snapshot.get("phase"), min_score)
        decay_snapshot = setup_decay_score(best, tech)
        if decay_snapshot.get("decay"):
            best["score"] = max(0, best["score"] - decay_snapshot["decay"] * 0.35)
            best.setdefault("reasons", []).append(
                "setup decay softened score: " + ", ".join(decay_snapshot.get("reasons") or [])
            )
        if best["score"] < adaptive_prefilter:
            print(f"{ticker}: skipped, ensemble score {best['score']} below adaptive floor {adaptive_prefilter} for phase {phase_snapshot.get('phase')}")
            return None

        if self.cooldown_active(ticker, best["direction"]):
            return None

        if best.get("late_breakout_risk") and best["score"] < 90:
            best["score"] = max(0, best["score"] - 12)
            best.setdefault("reasons", []).append(f"late breakout risk penalty: {best.get('late_reason')}")

        intraday_ok, intraday_info = intraday_confirmation(ticker, best)
        print(f"{ticker}: intraday={intraday_info.get('confirmations')}/{intraday_info.get('required_confirmations')} | approved={intraday_info.get('approved')} | reason={intraday_info.get('reason')}")
        if not intraday_ok:
            return None

        entry_mode, mode_reason = self.detect_entry_mode(best, tech, intraday_info)
        best["entry_mode"] = entry_mode
        best["entry_mode_reason"] = mode_reason
        print(f"{ticker}: entry_mode={entry_mode} - {mode_reason}")

        try:
            reasoning_input = dict(best)
            previous_reasoning = best.get("ai_reasoning") or {}
            if previous_reasoning.get("base_score") is not None:
                reasoning_input["score"] = previous_reasoning.get("base_score")
            reasoning = build_reasoning_report(
                ticker=ticker,
                setup=reasoning_input,
                tech=tech,
                bot=self,
                trade_type="INTRADAY",
            ) or {}
            best["ai_reasoning"] = reasoning
            best["score"] = reasoning.get("final_score", best.get("score", 0))
        except Exception as e:
            print(f"{ticker}: reasoning learning skipped: {e}")
            reasoning = {}
            best["ai_reasoning"] = {}

        if best["score"] >= 90:
            try:
                chart_path = await capture_chart(ticker, f"{ticker}.png")
                ai = self.ask_ai_with_chart(ticker, best, tech, intraday_info, entry_mode, mode_reason, chart_path)
            except Exception as e:
                print(f"{ticker}: chart capture failed: {e}")
                ai = self.ask_ai_decision(ticker, best, tech, intraday_info, entry_mode, mode_reason)
        else:
            ai = self.ask_ai_decision(ticker, best, tech, intraday_info, entry_mode, mode_reason)

        learning_context = (best.get("ai_reasoning") or {}).get("learning_context") or {
            "alert_type": "INTRADAY",
            "entry_mode": entry_mode,
            "direction": best.get("direction"),
        }
        learning_context.setdefault("setup_key", setup_structure_key(learning_context))
        confidence_learning = calibrate_confidence(ai.get("confidence", 0), learning_context)
        ai["base_confidence"] = confidence_learning["base_confidence"]
        ai["confidence"] = confidence_learning["calibrated_confidence"]
        ai["confidence_adjustment"] = confidence_learning["confidence_adjustment"]
        ai["learning_key"] = confidence_learning["learning_key"]
        ai["learning_stats"] = confidence_learning["learning_stats"]

        passes, gate_reason = self.ai_passes_gate(ai, best, intraday_info, entry_mode)
        if not passes:
            print(f"{ticker}: rejected - {gate_reason}")
            return None

        ranking_score = best["score"] + int(ai.get("confidence", 0)) + float(ai.get("risk_reward", 0)) * 10
        ranking_score += {"RETEST": 25, "BREAKOUT": 20, "MOMENTUM": 15, "PULLBACK": 10}.get(entry_mode, 5)
        if ai.get("setup_quality") == "A+":
            ranking_score += 20
        elif ai.get("setup_quality") == "A":
            ranking_score += 10
        if intraday_info.get("approved"):
            ranking_score += 15
        if intraday_info.get("confirmations", 0) >= 3:
            ranking_score += 10
        historical_priority_bonus = priority_bonus(learning_context)
        ranking_score += historical_priority_bonus
        if best.get("retest_confirmed"):
            ranking_score += 10

        options_flow = None
        try:
            options_flow = analyze_options_flow(ticker, best.get("direction"))
            best["options_flow"] = options_flow_to_dict(options_flow)
            if options_flow.status == "OK":
                if options_flow.bias == "BULLISH" and best.get("direction") == "CALL":
                    ranking_score += options_flow.score * 0.25
                elif options_flow.bias == "BEARISH" and best.get("direction") == "PUT":
                    ranking_score += options_flow.score * 0.25
                elif options_flow.bias in {"BULLISH", "BEARISH"}:
                    ranking_score -= 15
                if options_flow.gamma_squeeze and best.get("direction") == "CALL":
                    ranking_score += 15
        except Exception as e:
            print(f"{ticker}: options flow analysis skipped: {e}")

        try:
            option_contract = select_option_contract(
                ticker,
                {"signal": best.get("direction"), "price": ai.get("entry") or tech.get("price")},
                min_dte=INTRADAY_OPTION_MIN_DTE,
                max_dte=INTRADAY_OPTION_MAX_DTE,
                allow_default_fallback=INTRADAY_OPTION_ALLOW_DEFAULT_FALLBACK,
            )
            best["option_contract"] = option_to_dict(option_contract)
            missing_option_details = missing_option_contract_order_details(best["option_contract"])
            if missing_option_details:
                print(
                    f"{ticker}: rejected - no orderable option contract "
                    f"({', '.join(missing_option_details)})"
                )
                return None
            ranking_score += min(10, (option_contract.recommendation_score or 0) * 0.08)
        except Exception as e:
            print(f"{ticker}: rejected - option contract selection failed: {e}")
            return None

        try:
            reasoning_input = dict(best)
            previous_reasoning = best.get("ai_reasoning") or {}
            if previous_reasoning.get("base_score") is not None:
                reasoning_input["score"] = previous_reasoning.get("base_score")
            reasoning = build_reasoning_report(
                ticker=ticker,
                setup=reasoning_input,
                tech=tech,
                bot=self,
                trade_type="INTRADAY",
            ) or {}
            best["ai_reasoning"] = reasoning
            best["score"] = reasoning.get("final_score", best.get("score", 0))
        except Exception as e:
            print(f"{ticker}: options-aware reasoning refresh skipped: {e}")

        return {
            "ticker": ticker,
            "setup": best,
            "tech": tech,
            "ai": ai,
            "intraday": intraday_info,
            "entry_mode": entry_mode,
            "mode_reason": mode_reason,
            "ranking_score": ranking_score,
            "learning_context": learning_context,
            "historical_priority_bonus": historical_priority_bonus,
            "options_flow": options_flow,
        }

    async def check_ticker(self, ticker):
        try:
            await asyncio.sleep(0.15)
            if not self.is_regular_market_hours() or not self.is_quality_trading_window():
                return None
            return await self.build_candidate(ticker)
        except Exception as e:
            print(f"{ticker}: error {e}")
            return None


    def refresh_alert_price(self, ticker, tech):
        """Use a fresh entitled last trade for the displayed alert price when possible."""
        realtime_trade = self.get_realtime_stock_trade(ticker)
        if not realtime_trade:
            return tech

        now = dt.datetime.now(MARKET_TZ)
        trade_ts = realtime_trade["timestamp"]
        if trade_ts.date() != now.date():
            return tech

        if not (dt.time(9, 30) <= now.time() <= dt.time(16, 5)):
            return tech

        trade_age = (now - trade_ts).total_seconds()
        if not (0 <= trade_age <= REALTIME_STOCK_MAX_AGE_SEC):
            return tech

        refreshed = dict(tech)
        refreshed["price"] = realtime_trade["price"]
        refreshed["latest_price_time"] = trade_ts.strftime("%H:%M")
        refreshed["intraday_data_source"] = "realtime_trade_alert_refresh"
        refreshed["intraday_data_delay_sec"] = int(trade_age)
        refreshed["realtime_overlay_active"] = True
        return refreshed

    def alert(self, ticker, setup, tech, ai, intraday_info=None, entry_mode="STANDARD", mode_reason="", ranking_score=0, options_flow=None):
        tech = self.refresh_alert_price(ticker, tech)
        direction = setup["direction"]
        emoji = "🟢" if direction == "CALL" else "🔴"
        market = self.get_market_bias()
        alert_time = dt.datetime.now(dt.timezone.utc).isoformat()
        intraday_info = intraday_info or {}
        reasoning = setup.get("ai_reasoning") or {}
        learning_context = reasoning.get("learning_context") or {}
        learning_confidence = reasoning.get("learning_confidence") or {}
        learning_stats = ai.get("learning_stats") or learning_confidence.get("learning_stats") or {}
        priority = reasoning.get("priority_bonus", 0)
        setup_key = learning_context.get("setup_key") or setup_structure_key({"alert_type": "INTRADAY", "entry_mode": entry_mode, "direction": direction})
        options_flow = options_flow or setup.get("options_flow")
        option_contract = setup.get("option_contract")
        probabilities = reasoning.get("probabilities") or {}
        quality_rank = reasoning.get("quality_rank") or "n/a"
        no_trade_score = (reasoning.get("no_trade") or {}).get("score", 0)
        market_phase = (reasoning.get("market_phase") or {}).get("phase", "UNKNOWN")
        risk_plan = reasoning.get("risk_plan") or {}
        risk_action = risk_plan.get("action", "n/a")
        risk_multiplier = float(risk_plan.get("risk_multiplier") or 0)
        options_flow_text = ""
        if options_flow:
            if isinstance(options_flow, dict):
                flow_signals = options_flow.get("signals") or []
                top_signals = ", ".join(str(s.get("name")) for s in flow_signals[:4] if isinstance(s, dict)) or "none"
                options_flow_text = (
                    f"\n🧨 *Options Flow:* {options_flow.get('bias')} {options_flow.get('score')}/100 | "
                    f"Gamma: {options_flow.get('dealer_gamma_state')} | Squeeze: {options_flow.get('gamma_squeeze')}\n"
                    f"💵 *Premium:* Calls ${float(options_flow.get('call_premium') or 0):,.0f} / "
                    f"Puts ${float(options_flow.get('put_premium') or 0):,.0f} | Δ Net {float(options_flow.get('net_delta') or 0):,.0f}\n"
                    f"🧱 *Walls:* Put {options_flow.get('put_wall_strike') or 'n/a'} / "
                    f"Call {options_flow.get('call_wall_strike') or 'n/a'} | Signals: {top_signals}\n"
                )
            else:
                options_flow_text = "\n" + format_options_flow(options_flow) + "\n"

        predicted_move_text = format_predicted_price_move(
            direction,
            ai.get("entry"),
            ai.get("target"),
            ai.get("stop"),
        )
        option_contract_text = ""
        if option_contract:
            if not has_valid_option_contract_order_details(option_contract):
                print(f"{ticker}: alert blocked - missing valid option contract details")
                return False
            if isinstance(option_contract, dict):
                option_contract_text = format_recommended_option_contract(
                    option_contract,
                    direction=direction,
                    entry=ai.get("entry"),
                    target=ai.get("target"),
                    include_skip_reason=False,
                )
            else:
                option_contract_text = format_recommended_option_contract(
                    option_contract,
                    direction=direction,
                    entry=ai.get("entry"),
                    target=ai.get("target"),
                    include_skip_reason=False,
                )
        else:
            print(f"{ticker}: alert blocked - no option contract recommendation")
            return False

        msg = (
            f"{emoji} *{entry_mode} {direction} SETUP: {ticker}*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 *Day:* {tech['trading_day']}\n"
            f"💰 *Price:* ${fmt_price(tech['price'])}\n"
            f"🕒 *Price Source:* {tech.get('intraday_data_source', 'unknown')} "
            f"@ {tech.get('latest_price_time') or 'n/a'} ET "
            f"(delay {tech.get('intraday_data_delay_sec', 'n/a')}s, "
            f"RT overlay {tech.get('realtime_overlay_active')})\n"
            f"⭐ *AI Score:* {setup['score']}/100 | *Rule:* {setup.get('rule_score')}\n"
            f"🏅 *Rank Score:* {ranking_score:.1f} | *Tier:* {quality_rank}\n"
            f"🧭 *Phase:* {market_phase} | *No-Trade:* {no_trade_score}/100\n"
            f"📈 *Prob:* Win {float(probabilities.get('win_probability', 0)) * 100:.0f}% | Trap {float(probabilities.get('trap_probability', 0)) * 100:.0f}%\n"
            f"🛡️ *Phase 5 Risk:* {risk_action} | Size {risk_multiplier:.2f}x | Max ${float(risk_plan.get('max_risk_dollars') or 0):.0f}\n"
            f"🎯 *Mode:* {entry_mode} — {mode_reason}\n"
            f"🤖 *AI:* {ai['verdict']} ({ai['confidence']}%) | Hist Adj {ai.get('confidence_adjustment', 0):+.1f}\n"
            f"🏆 *Quality:* {ai['setup_quality']} | *Timing:* {ai['entry_timing']}\n"
            f"🌎 *ETF Bias:* {market['bias']} ({market['bullish_count']} bull / {market['bearish_count']} bear)\n"
            f"📊 *Intraday:* {intraday_info.get('confirmations')}/{intraday_info.get('required_confirmations')} | {intraday_info.get('reason')}\n"
            f"📚 *History:* WR {float(learning_stats.get('win_rate', 0)) * 100:.1f}% | Forecast {float(learning_stats.get('forecast_accuracy', 0)) * 100:.1f}% | Priority {priority:+.1f}\n\n"
            f"🎯 *Entry:* {fmt_price(ai['entry'])}\n"
            f"🛑 *Stop:* {fmt_price(ai['stop'])}\n"
            f"🚀 *Target:* {fmt_price(ai['target'])}\n"
            f"{predicted_move_text}"
            f"📐 *R/R:* {float(ai['risk_reward'] or 0):.2f}:1\n"
            f"📏 *ATR14:* {fmt_price(tech['atr14'])}\n\n"
            f"📍 *VWAP:* {fmt_price(tech['vwap'])}\n"
            f"📈 *EMA9/21/50:* {fmt_price(tech['ema9'])} / {fmt_price(tech['ema21'])} / {fmt_price(tech['ema50'])}\n"
            f"🟦 *ORB H/L:* {fmt_price(tech['orb_high'])} / {fmt_price(tech['orb_low'])}\n"
            f"🌅 *PM H/L:* {fmt_price(tech['premarket_high'])} / {fmt_price(tech['premarket_low'])}\n"
            f"📆 *PD H/L:* {fmt_price(tech['prev_high'])} / {fmt_price(tech['prev_low'])}\n"
            f"📊 *Vol:* {tech['current_volume']} / Avg20 {tech['avg_20_volume']}\n"
            f"{options_flow_text}"
            f"{option_contract_text}\n"
            f"🔥 *Retest:* {ai['retest_confirmed']}\n"
            f"⚠️ *Late Risk:* {ai['late_breakout_risk']}\n\n"
            f"📝 *AI Reason:* {ai['reason']}\n\n"
            f"🧠 *Dynamic Trade Thesis:*\n{(setup.get('ai_reasoning') or {}).get('narrative', 'n/a')}\n\n"
            f"🔎 *Rule Reasons:* {', '.join(setup.get('reasons', []))}\n"
            f"🌎 *ETF Details:* {', '.join(market['details'])}"
        )

        telegram_sent = bool(self.send_telegram_msg(msg))
        if not telegram_sent:
            print(f"{ticker}: telegram send failed; intraday alert not counted or ordered")
            return False

        if risk_action == "WATCH_ONLY":
            print(f"{ticker}: Phase 5 risk plan is WATCH_ONLY; skipping automated option buy")
        else:
            maybe_buy_recommended_option(
                ticker=ticker,
                direction=direction,
                option_contract=option_contract or {},
                telegram_sender=self.send_telegram_msg,
            )

        mark_alerted_today(ticker)

        log_alert({
            "timestamp": alert_time,
            "ticker": ticker,
            "direction": direction,
            "entry_mode": entry_mode,
            "score": setup["score"],
            "rule_score": setup.get("rule_score"),
            "ranking_score": ranking_score,
            "ai_verdict": ai["verdict"],
            "ai_confidence": ai["confidence"],
            "calibrated_confidence": ai.get("confidence"),
            "confidence_adjustment": ai.get("confidence_adjustment"),
            "setup_quality": ai["setup_quality"],
            "entry_timing": ai["entry_timing"],
            "entry": ai["entry"],
            "stop": ai["stop"],
            "target": ai["target"],
            "risk_reward": ai["risk_reward"],
            "retest_confirmed": ai["retest_confirmed"],
            "late_breakout_risk": ai["late_breakout_risk"],
            "ai_reason": ai["reason"],
            "price": tech["price"],
            "latest_price_time": tech.get("latest_price_time"),
            "latest_regular_time": tech.get("latest_regular_time"),
            "intraday_data_source": tech.get("intraday_data_source"),
            "intraday_data_delay_sec": tech.get("intraday_data_delay_sec"),
            "realtime_overlay_active": tech.get("realtime_overlay_active"),
            "vwap": tech["vwap"],
            "ema9": tech["ema9"],
            "ema21": tech["ema21"],
            "ema50": tech["ema50"],
            "dma20": tech["dma20"],
            "dma50": tech["dma50"],
            "dma200": tech["dma200"],
            "atr14": tech["atr14"],
            "trend_5m": tech["trend_5m"],
            "trend_15m": tech["trend_15m"],
            "orb_high": tech["orb_high"],
            "orb_low": tech["orb_low"],
            "premarket_high": tech["premarket_high"],
            "premarket_low": tech["premarket_low"],
            "prev_high": tech["prev_high"],
            "prev_low": tech["prev_low"],
            "current_volume": tech["current_volume"],
            "avg_20_volume": tech["avg_20_volume"],
            "intraday_confirmations": intraday_info.get("confirmations"),
            "intraday_required": intraday_info.get("required_confirmations"),
            "intraday_reason": intraday_info.get("reason"),
            "market_bias": market["bias"],
            "market_details": ", ".join(market["details"]),
            "market_regime": (reasoning.get("regime") or {}).get("regime"),
            "market_phase": (reasoning.get("market_phase") or {}).get("phase"),
            "ensemble_score": reasoning.get("ensemble_score"),
            "quality_rank": reasoning.get("quality_rank"),
            "win_probability": (reasoning.get("probabilities") or {}).get("win_probability"),
            "trap_probability": (reasoning.get("probabilities") or {}).get("trap_probability"),
            "no_trade_score": (reasoning.get("no_trade") or {}).get("score"),
            "risk_action": risk_action,
            "risk_multiplier": risk_plan.get("risk_multiplier"),
            "max_risk_dollars": risk_plan.get("max_risk_dollars"),
            "phase4_context_key": (reasoning.get("context_memory") or {}).get("key"),
            "phase4_context_adjustment": (reasoning.get("context_memory") or {}).get("score_adjustment"),
            "mtf_structure": (reasoning.get("mtf") or {}).get("structure"),
            "chart_structure": (reasoning.get("vision") or {}).get("quality"),
            "setup_key": setup_key,
            "learning_key": ai.get("learning_key") or learning_confidence.get("learning_key"),
            "learning_win_rate": learning_stats.get("win_rate"),
            "forecast_accuracy": learning_stats.get("forecast_accuracy"),
            "priority_bonus": priority,
            "reasons": ", ".join(setup.get("reasons", [])),
            "atr_extension": tech.get("atr_extension") or tech.get("breakout_distance_atr"),
            "wick_ratio": tech.get("wick_ratio"),
            "candle_body_pct": tech.get("candle_body_pct") or tech.get("body_pct"),
            "distance_from_vwap": tech.get("distance_from_vwap"),
            "distance_from_ema21": tech.get("distance_from_ema21") or tech.get("price_vs_ema21_pct"),
            "rel_volume": tech.get("rel_volume"),
            "spread_pct": option_contract.get("spread_pct") if isinstance(option_contract, dict) else getattr(option_contract, "spread_pct", None),
            "option_volume": option_contract.get("volume") if isinstance(option_contract, dict) else getattr(option_contract, "volume", None),
            "open_interest": option_contract.get("open_interest") if isinstance(option_contract, dict) else getattr(option_contract, "open_interest", None),
            "sector_relative_strength": tech.get("sector_relative_strength"),
            "deep_ai_approval": ai.get("verdict"),
            "deep_ai_rejection_reason": "" if ai.get("verdict") == "BUY" else ai.get("reason"),
            "options_flow_bias": (options_flow.get("bias") if isinstance(options_flow, dict) else getattr(options_flow, "bias", None)),
            "options_flow_score": (options_flow.get("score") if isinstance(options_flow, dict) else getattr(options_flow, "score", None)),
            "options_flow_gamma_squeeze": (options_flow.get("gamma_squeeze") if isinstance(options_flow, dict) else getattr(options_flow, "gamma_squeeze", None)),
        })

        if ai["entry"] and ai["stop"] and ai["target"]:
            outcome = track_outcome(
                ticker=ticker,
                direction=direction,
                entry=float(ai["entry"]),
                stop=float(ai["stop"]),
                target=float(ai["target"]),
                alert_time_iso=alert_time,
                alert_type="INTRADAY",
                entry_mode=entry_mode,
                setup_context={
                    "setup_key": setup_key,
                    "market_regime": (reasoning.get("regime") or {}).get("regime"),
                    "market_phase": (reasoning.get("market_phase") or {}).get("phase"),
                    "ensemble_score": reasoning.get("ensemble_score"),
                    "quality_rank": reasoning.get("quality_rank"),
                    "win_probability": (reasoning.get("probabilities") or {}).get("win_probability"),
                    "trap_probability": (reasoning.get("probabilities") or {}).get("trap_probability"),
                    "no_trade_score": (reasoning.get("no_trade") or {}).get("score"),
                    "mtf_structure": (reasoning.get("mtf") or {}).get("structure"),
                    "chart_structure": (reasoning.get("vision") or {}).get("quality"),
                    "ai_confidence": ai.get("base_confidence"),
                    "calibrated_confidence": ai.get("confidence"),
                    "score": setup.get("score"),
                    "tech": tech,
                    "setup": setup,
                    "ai": ai,
                    "reasoning": reasoning,
                    "option_contract": setup.get("option_contract"),
                    "options_flow": setup.get("options_flow"),
                    "atr_extension": tech.get("atr_extension") or tech.get("breakout_distance_atr"),
                    "wick_ratio": tech.get("wick_ratio"),
                    "candle_body_pct": tech.get("candle_body_pct") or tech.get("body_pct"),
                    "distance_from_vwap": tech.get("distance_from_vwap"),
                    "distance_from_ema21": tech.get("distance_from_ema21") or tech.get("price_vs_ema21_pct"),
                    "rel_volume": tech.get("rel_volume"),
                    "sector_relative_strength": tech.get("sector_relative_strength"),
                    "deep_ai_approval": ai.get("verdict"),
                    "deep_ai_rejection_reason": "" if ai.get("verdict") == "BUY" else ai.get("reason"),
                },
            )
            if outcome:
                print(f"{ticker}: outcome={outcome['result']} max_gain={outcome['max_gain_pct']}% max_loss={outcome['max_loss_pct']}%")

        return True


    def maybe_manage_option_positions(self, *, force=False):
        now = dt.datetime.now(dt.timezone.utc)
        last_check = getattr(self, "_last_option_management_check", None)
        if (
            not force
            and last_check
            and (now - last_check).total_seconds() < OPTION_PRICE_CHECK_INTERVAL_SEC
        ):
            return []

        closed = manage_open_option_positions(telegram_sender=self.send_telegram_msg)
        self._last_option_management_check = now
        return closed

    async def sleep_with_option_management(self, seconds):
        remaining = max(0, float(seconds))
        while remaining > 0:
            chunk = min(remaining, max(1, OPTION_PRICE_CHECK_INTERVAL_SEC))
            await asyncio.sleep(chunk)
            remaining -= chunk
            if remaining > 0:
                self.maybe_manage_option_positions()

    def maybe_send_daily_learning_report(self):
        now = dt.datetime.now(dt.timezone.utc)
        if now.hour < 21:
            return

        sent_for = getattr(self, "_daily_learning_report_sent_for", None)
        if sent_for == now.date().isoformat():
            return

        try:
            send_daily_learning_report(self)
            self._daily_learning_report_sent_for = now.date().isoformat()
        except Exception as e:
            print(f"Daily learning report skipped: {e}")


    async def run(self):
        print("🚀 Stock Technical AI Bot Running")

        while True:
            try:
                self.maybe_manage_option_positions()

                if not self.is_regular_market_hours() or not self.is_quality_trading_window():
                    self.maybe_send_daily_learning_report()
                    print("⏸ Outside quality market window | sleeping 600s")
                    await self.sleep_with_option_management(600)
                    continue

                self.tickers = self.get_auto_watchlist()
                candidates = []
                for ticker in self.tickers:
                    candidate = await self.check_ticker(ticker)
                    if candidate:
                        candidates.append(candidate)

                candidates.sort(key=lambda x: x["ranking_score"], reverse=True)
                selected = candidates[:MAX_ALERTS_PER_SCAN] if RANK_TOP_ALERTS_ONLY else candidates

                for c in selected:
                    alert_sent = self.alert(
                        c["ticker"],
                        c["setup"],
                        c["tech"],
                        c["ai"],
                        c.get("intraday"),
                        c.get("entry_mode", "STANDARD"),
                        c.get("mode_reason", ""),
                        c["ranking_score"],
                        c.get("options_flow"),
                    )
                    if alert_sent:
                        self.mark_alert(c["ticker"], c["setup"]["direction"])

                print(f"✅ Scan complete | candidates={len(candidates)} | sent={len(selected)} | sleeping {SCAN_INTERVAL_SEC}s")
                await self.sleep_with_option_management(SCAN_INTERVAL_SEC)
            except Exception as e:
                print(f"Scan loop error: {e}")
                await self.sleep_with_option_management(SCAN_INTERVAL_SEC)

