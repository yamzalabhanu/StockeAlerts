from config import *
from openai import OpenAI

import requests
import asyncio
import datetime as dt
import csv
import base64
from typing import Dict, Any

from bot_technical import StockTechnicalBase
from bot_utils import fmt_price, extract_gpt_json, normalize_ai_response
from outcome_tracker import track_outcome
from chart_capture import capture_chart
from intraday_confirm import intraday_confirmation
from ai_scoring import ai_score_setup
from ai_reasoning_engine import build_reasoning_report
from performance_learning import calibrate_confidence, priority_bonus, setup_structure_key
from daily_report_engine import send_daily_learning_report


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
        "price", "vwap", "ema9", "ema21", "ema50",
        "dma20", "dma50", "dma200", "atr14",
        "trend_5m", "trend_15m", "orb_high", "orb_low",
        "premarket_high", "premarket_low", "prev_high", "prev_low",
        "current_volume", "avg_20_volume",
        "intraday_confirmations", "intraday_required", "intraday_reason",
        "market_bias", "market_details", "market_regime", "mtf_structure", "chart_structure", "setup_key", "learning_key", "learning_win_rate", "forecast_accuracy", "priority_bonus", "reasons",
    ]

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


class StockTechnicalAIBot(StockTechnicalBase):
    def send_telegram_msg(self, msg):
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            print(msg)
            return

        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception as e:
            print(f"Telegram error: {e}")

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
                model="gpt-4o-mini",
                temperature=0.1,
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
                model="gpt-4o-mini",
                temperature=0.1,
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
        if ai.get("verdict") == "BUY" and confidence >= MIN_AI_CONFIDENCE:
            return True, "AI approved"
        if score >= 80 and confirmations >= 3 and entry_mode in {"BREAKOUT", "RETEST", "MOMENTUM"} and rr >= MIN_RISK_REWARD:
            return True, "override: strong AI-scored setup with intraday confirmation"
        return False, ai.get("reason", "AI did not approve")

    async def build_candidate(self, ticker):
        tech = self.get_technical_context(ticker)
        if not tech:
            return None

        call = self.apply_ai_scoring(ticker, tech, self.score_call_setup(tech))
        put = self.apply_ai_scoring(ticker, tech, self.score_put_setup(tech))
        best = call if call["score"] >= put["score"] else put
        min_score = MIN_CALL_SCORE if best["direction"] == "CALL" else MIN_PUT_SCORE

        print(
            f"{ticker}: price={fmt_price(tech['price'])}, "
            f"CALL_AI={call['score']} (rule={call.get('rule_score')}), "
            f"PUT_AI={put['score']} (rule={put.get('rule_score')}), best={best['direction']}"
        )

        if best["score"] < min_score:
            print(f"{ticker}: skipped, AI score {best['score']} below {min_score}")
            return None

        if self.cooldown_active(ticker, best["direction"]):
            return None

        if best.get("late_breakout_risk") and best["score"] < 90:
            print(f"{ticker}: skipped, late breakout risk - {best.get('late_reason')}")
            return None

        intraday_ok, intraday_info = intraday_confirmation(ticker, best)
        print(f"{ticker}: intraday={intraday_info.get('confirmations')}/{intraday_info.get('required_confirmations')} | approved={intraday_info.get('approved')} | reason={intraday_info.get('reason')}")
        if not intraday_ok:
            return None

        entry_mode, mode_reason = self.detect_entry_mode(best, tech, intraday_info)
        best["entry_mode"] = entry_mode
        best["entry_mode_reason"] = mode_reason
        print(f"{ticker}: entry_mode={entry_mode} - {mode_reason}")

        try:
            reasoning = build_reasoning_report(
                ticker=ticker,
                setup=best,
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

    def alert(self, ticker, setup, tech, ai, intraday_info=None, entry_mode="STANDARD", mode_reason="", ranking_score=0):
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

        msg = (
            f"{emoji} *{entry_mode} {direction} SETUP: {ticker}*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 *Day:* {tech['trading_day']}\n"
            f"💰 *Price:* ${fmt_price(tech['price'])}\n"
            f"⭐ *AI Score:* {setup['score']}/100 | *Rule:* {setup.get('rule_score')}\n"
            f"🏅 *Rank Score:* {ranking_score:.1f}\n"
            f"🎯 *Mode:* {entry_mode} — {mode_reason}\n"
            f"🤖 *AI:* {ai['verdict']} ({ai['confidence']}%) | Hist Adj {ai.get('confidence_adjustment', 0):+.1f}\n"
            f"🏆 *Quality:* {ai['setup_quality']} | *Timing:* {ai['entry_timing']}\n"
            f"🌎 *ETF Bias:* {market['bias']} ({market['bullish_count']} bull / {market['bearish_count']} bear)\n"
            f"📊 *Intraday:* {intraday_info.get('confirmations')}/{intraday_info.get('required_confirmations')} | {intraday_info.get('reason')}\n"
            f"📚 *History:* WR {float(learning_stats.get('win_rate', 0)) * 100:.1f}% | Forecast {float(learning_stats.get('forecast_accuracy', 0)) * 100:.1f}% | Priority {priority:+.1f}\n\n"
            f"🎯 *Entry:* {fmt_price(ai['entry'])}\n"
            f"🛑 *Stop:* {fmt_price(ai['stop'])}\n"
            f"🚀 *Target:* {fmt_price(ai['target'])}\n"
            f"📐 *R/R:* {float(ai['risk_reward'] or 0):.2f}:1\n"
            f"📏 *ATR14:* {fmt_price(tech['atr14'])}\n\n"
            f"📍 *VWAP:* {fmt_price(tech['vwap'])}\n"
            f"📈 *EMA9/21/50:* {fmt_price(tech['ema9'])} / {fmt_price(tech['ema21'])} / {fmt_price(tech['ema50'])}\n"
            f"🟦 *ORB H/L:* {fmt_price(tech['orb_high'])} / {fmt_price(tech['orb_low'])}\n"
            f"🌅 *PM H/L:* {fmt_price(tech['premarket_high'])} / {fmt_price(tech['premarket_low'])}\n"
            f"📆 *PD H/L:* {fmt_price(tech['prev_high'])} / {fmt_price(tech['prev_low'])}\n"
            f"📊 *Vol:* {tech['current_volume']} / Avg20 {tech['avg_20_volume']}\n\n"
            f"🔥 *Retest:* {ai['retest_confirmed']}\n"
            f"⚠️ *Late Risk:* {ai['late_breakout_risk']}\n\n"
            f"📝 *AI Reason:* {ai['reason']}\n\n"
            f"🔎 *Rule Reasons:* {', '.join(setup.get('reasons', []))}\n"
            f"🌎 *ETF Details:* {', '.join(market['details'])}"
        )

        self.send_telegram_msg(msg)

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
            "mtf_structure": (reasoning.get("mtf") or {}).get("structure"),
            "chart_structure": (reasoning.get("vision") or {}).get("quality"),
            "setup_key": setup_key,
            "learning_key": ai.get("learning_key") or learning_confidence.get("learning_key"),
            "learning_win_rate": learning_stats.get("win_rate"),
            "forecast_accuracy": learning_stats.get("forecast_accuracy"),
            "priority_bonus": priority,
            "reasons": ", ".join(setup.get("reasons", [])),
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
                    "mtf_structure": (reasoning.get("mtf") or {}).get("structure"),
                    "chart_structure": (reasoning.get("vision") or {}).get("quality"),
                    "ai_confidence": ai.get("base_confidence"),
                    "calibrated_confidence": ai.get("confidence"),
                    "score": setup.get("score"),
                },
            )
            if outcome:
                print(f"{ticker}: outcome={outcome['result']} max_gain={outcome['max_gain_pct']}% max_loss={outcome['max_loss_pct']}%")

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

            if not self.is_regular_market_hours() or not self.is_quality_trading_window():
                self.maybe_send_daily_learning_report()
                print("⏸ Outside quality market window | sleeping 600s")
                await asyncio.sleep(600)
                continue

                outside_intraday = (
                    not self.is_regular_market_hours()
                    or not self.is_quality_trading_window()
                )

                if outside_intraday:
                    print("📈 Swing scan mode | intraday disabled")

                self.tickers = self.get_auto_watchlist()

                candidates = []

                for ticker in self.tickers:
                    candidate = await self.check_ticker(ticker)

                    if candidate:
                        candidates.append(candidate)

                candidates.sort(
                    key=lambda x: x["ranking_score"],
                    reverse=True
                )

                selected = (
                    candidates[:MAX_ALERTS_PER_SCAN]
                    if RANK_TOP_ALERTS_ONLY
                    else candidates
                )

                for c in selected:
                    self.alert(
                        c["ticker"],
                        c["setup"],
                        c["tech"],
                        c["ai"],
                        c.get("intraday"),
                        c.get("entry_mode", "STANDARD"),
                        c.get("mode_reason", ""),
                        c["ranking_score"],
                    )

                    self.mark_alert(
                        c["ticker"],
                        c["setup"]["direction"]
                    )

                print(
                    f"✅ Scan complete | "
                    f"candidates={len(candidates)} | "
                    f"sent={len(selected)} | "
                    f"sleeping {SCAN_INTERVAL_SEC}s"
                )

                await asyncio.sleep(SCAN_INTERVAL_SEC)

            except Exception as e:
                print(f"Run loop error: {e}")
                await asyncio.sleep(60)

