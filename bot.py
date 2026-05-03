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


ai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def log_alert(row: Dict[str, Any]):
    file_exists = False

    try:
        with open(LOG_FILE, "r"):
            file_exists = True
    except FileNotFoundError:
        pass

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "timestamp", "ticker", "direction", "score", "ranking_score",
            "ai_verdict", "ai_confidence", "setup_quality", "entry_timing",
            "entry", "stop", "target", "risk_reward",
            "retest_confirmed", "late_breakout_risk", "ai_reason",
            "price", "vwap", "ema9", "ema21", "ema50",
            "dma20", "dma50", "dma200", "atr14",
            "trend_5m", "trend_15m",
            "orb_high", "orb_low",
            "premarket_high", "premarket_low",
            "prev_high", "prev_low",
            "current_volume", "avg_20_volume",
            "intraday_confirmations", "intraday_required", "intraday_reason",
            "market_bias", "market_details",
            "reasons"
        ])

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
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": msg,
                    "parse_mode": "Markdown"
                },
                timeout=10
            )
        except Exception as e:
            print(f"Telegram error: {e}")

    def fallback_atr_trade_plan(self, setup, tech):
        entry = tech["price"]
        atr = tech.get("atr14")

        if not atr:
            return entry, None, None, 0

        if setup["direction"] == "CALL":
            stop = entry - (atr * ATR_STOP_MULTIPLIER)
            target = entry + (atr * ATR_TARGET_MULTIPLIER)
            risk = entry - stop
            reward = target - entry
        else:
            stop = entry + (atr * ATR_STOP_MULTIPLIER)
            target = entry - (atr * ATR_TARGET_MULTIPLIER)
            risk = stop - entry
            reward = entry - target

        rr = reward / risk if risk > 0 else 0
        return entry, stop, target, rr

    def encode_image(self, path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def ask_ai_decision(self, ticker, setup, tech):
        market = self.get_market_bias()
        fallback_entry, fallback_stop, fallback_target, fallback_rr = self.fallback_atr_trade_plan(setup, tech)

        if not ai_client:
            return {
                "verdict": "BUY" if setup["score"] >= 80 else "WAIT",
                "confidence": setup["score"],
                "entry": fallback_entry,
                "stop": fallback_stop,
                "target": fallback_target,
                "risk_reward": fallback_rr,
                "setup_quality": "A" if setup["score"] >= 85 else "B",
                "entry_timing": "IDEAL",
                "retest_confirmed": setup.get("retest_confirmed", False),
                "late_breakout_risk": setup.get("late_breakout_risk", True),
                "reason": "OpenAI not configured; ATR-based rule score only."
            }

        prompt = f"""
Analyze this intraday stock technical setup like a disciplined scalping trader.

Ticker: {ticker}
Direction Candidate: {setup["direction"]}
Rule Score: {setup["score"]}
Rule Reasons: {", ".join(setup["reasons"])}

Technical Data:
Trading Day: {tech["trading_day"]}
Price: {tech["price"]}
VWAP: {tech["vwap"]}
EMA9: {tech["ema9"]}
EMA21: {tech["ema21"]}
EMA50: {tech["ema50"]}
DMA20: {tech["dma20"]}
DMA50: {tech["dma50"]}
DMA200: {tech["dma200"]}
ATR14: {tech["atr14"]}
5m Trend: {tech["trend_5m"]}
15m Trend: {tech["trend_15m"]}
ORB High: {tech["orb_high"]}
ORB Low: {tech["orb_low"]}
Premarket High: {tech["premarket_high"]}
Premarket Low: {tech["premarket_low"]}
Previous Day High: {tech["prev_high"]}
Previous Day Low: {tech["prev_low"]}
Recent High: {tech["recent_high"]}
Recent Low: {tech["recent_low"]}
Previous Recent High: {tech["previous_recent_high"]}
Previous Recent Low: {tech["previous_recent_low"]}

Volume:
Current Volume: {tech["current_volume"]}
Avg 20-Bar Volume: {tech["avg_20_volume"]}

ATR Suggested Plan:
Entry: {fallback_entry}
Stop: {fallback_stop}
Target: {fallback_target}
Risk/Reward: {fallback_rr}

Market ETF Bias:
Bias: {market["bias"]}
Bullish ETFs: {market["bullish_count"]}
Bearish ETFs: {market["bearish_count"]}
Details: {", ".join(market["details"])}

Retest / Chase Filters:
Retest Confirmed: {setup.get("retest_confirmed")}
Late Breakout Risk: {setup.get("late_breakout_risk")}
Late Reason: {setup.get("late_reason")}

A+ Breakout Requirement:
For CALL A+ setup, price should be above premarket high or previous day high.
For PUT A+ setup, price should be below premarket low or previous day low.
If this condition is not met, downgrade setup_quality and prefer WAIT unless the setup is only a lower-grade scalp with exceptional structure.

Sector ETF Confirmation:
Use sector ETF confirmation when available.
If sector ETF conflicts with the individual stock setup, downgrade quality or choose WAIT.

Decision Framework:
1. Avoid chasing late breakouts/breakdowns.
2. Prefer A+ setups where price broke a meaningful level, retested, and reclaimed/rejected that level.
3. Prefer 5m/15m alignment, but allow A-quality trades when 5m trend is aligned and 15m is neutral, as long as VWAP/EMA/volume/breakout structure supports the trade.
4. Avoid CALLs directly below resistance, but allow if price is breaking/reclaiming resistance with momentum, volume expansion, and defined stop.
5. Do not approve PUTs directly above support.
6. Reject failed breakouts/breakdowns.
7. Use ATR for realistic stop/target.
8. Use ETF bias, relative strength vs SPY, volume spike, and continuation candles.
9. Risk/reward must be at least {MIN_RISK_REWARD}:1 for BUY.
10. Do not mark setup_quality as A+ unless the A+ Breakout Requirement is satisfied.

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
  "reason": "2-3 sentence explanation including price action, A+ breakout requirement, ETF bias, 5m/15m trend, volume/relative strength, breakout/retest quality, invalidation, and ATR target logic."
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
                            "You are an elite intraday scalping trader, risk manager, and trade-quality filter. "
                            "Decide whether the setup is worth taking NOW. Be conservative. "
                            "A+ CALL setups require price above premarket high or previous day high. "
                            "A+ PUT setups require price below premarket low or previous day low. "
                            "Prefer A+ setups, but allow A-quality trades when price action is bullish/bearish, risk/reward is favorable, and only one minor filter is missing. "
                            "Do not reject only because 15m trend is neutral if 5m trend, VWAP, volume, and breakout/retest are strong. "
                            "Do not reject only because price is near resistance if price is breaking above it with momentum, volume expansion, and stop is clearly defined. "
                            "Still reject choppy, late, extended, failed-breakout, unsupported, or poor risk/reward setups."
                        )
                    },
                    {"role": "user", "content": prompt}
                ]
            )

            data = extract_gpt_json(r.choices[0].message.content or "")
            return normalize_ai_response(data)

        except Exception as e:
            return {
                "verdict": "WAIT",
                "confidence": 50,
                "entry": None,
                "stop": None,
                "target": None,
                "risk_reward": 0,
                "setup_quality": "LOW",
                "entry_timing": "UNKNOWN",
                "retest_confirmed": False,
                "late_breakout_risk": True,
                "reason": f"OpenAI error: {e}"
            }

    def ask_ai_with_chart(self, ticker, setup, tech, image_path):
        if not ai_client:
            return self.ask_ai_decision(ticker, setup, tech)

        market = self.get_market_bias()
        fallback_entry, fallback_stop, fallback_target, fallback_rr = self.fallback_atr_trade_plan(setup, tech)

        try:
            base64_image = self.encode_image(image_path)

            prompt = f"""
Analyze BOTH the chart image and technical data for this intraday setup.

Ticker: {ticker}
Direction Candidate: {setup["direction"]}
Rule Score: {setup["score"]}
Rule Reasons: {", ".join(setup["reasons"])}

Price: {tech["price"]}
VWAP: {tech["vwap"]}
EMA9: {tech["ema9"]}
EMA21: {tech["ema21"]}
EMA50: {tech["ema50"]}
DMA20: {tech["dma20"]}
DMA50: {tech["dma50"]}
DMA200: {tech["dma200"]}
ATR14: {tech["atr14"]}
5m Trend: {tech["trend_5m"]}
15m Trend: {tech["trend_15m"]}
ORB High/Low: {tech["orb_high"]}/{tech["orb_low"]}
Premarket High/Low: {tech["premarket_high"]}/{tech["premarket_low"]}
Previous Day High/Low: {tech["prev_high"]}/{tech["prev_low"]}
Recent High/Low: {tech["recent_high"]}/{tech["recent_low"]}

ATR Suggested Plan:
Entry: {fallback_entry}
Stop: {fallback_stop}
Target: {fallback_target}
Risk/Reward: {fallback_rr}

ETF Bias:
Bias: {market["bias"]}
Details: {", ".join(market["details"])}

Visual Review Rules:
- Confirm breakout or breakdown structure visually.
- Confirm retest quality.
- Reject fake breakouts, long-wick rejection, chop, or late extended moves.
- Check whether price is directly below resistance for CALLs or above support for PUTs.
- A+ CALL requires price above premarket high or previous day high.
- A+ PUT requires price below premarket low or previous day low.
- Risk/reward must be at least {MIN_RISK_REWARD}:1.

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
  "reason": "2-3 sentence explanation using chart structure plus technical data."
}}
"""

            response = ai_client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.1,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a professional intraday chart reader and scalping risk manager. "
                            "Use the image to validate or reject the structured technical signal. "
                            "Prefer WAIT if the chart shows chop, failed breakout, wick rejection, or late entry risk."
                        )
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                },
                            },
                        ],
                    },
                ],
            )

            data = extract_gpt_json(response.choices[0].message.content or "")
            return normalize_ai_response(data)

        except Exception as e:
            print(f"{ticker}: vision AI error: {e}")
            return self.ask_ai_decision(ticker, setup, tech)

    async def build_candidate(self, ticker):
        tech = self.get_technical_context(ticker)
        if not tech:
            return None

        call = self.score_call_setup(tech)
        put = self.score_put_setup(tech)

        best = call if call["score"] >= put["score"] else put
        min_score = MIN_CALL_SCORE if best["direction"] == "CALL" else MIN_PUT_SCORE

        # Print only strong setups (>=100 score)
        if call["score"] >= 100 or put["score"] >= 100:
            print(
                f"{ticker}: price={fmt_price(tech['price'])}, "
                f"CALL={call['score']}, PUT={put['score']}, best={best['direction']}"
            )

        if best["score"] < min_score:
            return None

        if self.cooldown_active(ticker, best["direction"]):
            return None

        if REQUIRE_RETEST and not best.get("retest_confirmed"):
            print(f"{ticker}: skipped, retest not confirmed")
            return None

        if best.get("late_breakout_risk"):
            print(f"{ticker}: skipped, late breakout risk - {best.get('late_reason')}")
            return None

        intraday_ok, intraday_info = intraday_confirmation(ticker, best)
        print(
            f"{ticker}: intraday={intraday_info.get('confirmations')}/"
            f"{intraday_info.get('required_confirmations')} | "
            f"approved={intraday_info.get('approved')} | "
            f"reason={intraday_info.get('reason')}"
        )

        if not intraday_ok:
            print(f"{ticker}: rejected by intraday - {intraday_info.get('reason')}")
            return None

        if best["score"] >= 90:
            try:
                chart_path = await capture_chart(ticker, f"{ticker}.png")
                ai = self.ask_ai_with_chart(ticker, best, tech, chart_path)
            except Exception as e:
                print(f"{ticker}: chart capture failed: {e}")
                ai = self.ask_ai_decision(ticker, best, tech)
        else:
            ai = self.ask_ai_decision(ticker, best, tech)

        if ai["setup_quality"] not in ["A+", "A"]:
            print(f"{ticker}: rejected low quality {ai['setup_quality']}")
            return None
        if ai["verdict"] != "BUY":
            print(f"{ticker}: AI rejected {best['direction']} - {ai['reason']}")
            return None

        if ai["confidence"] < MIN_AI_CONFIDENCE:
            print(f"{ticker}: AI confidence too low {ai['confidence']}%")
            return None

        if ai["risk_reward"] < MIN_RISK_REWARD:
            print(f"{ticker}: rejected, RR too low {ai['risk_reward']}")
            return None

        if ai["entry_timing"] in ["LATE", "CHOP"]:
            print(f"{ticker}: rejected, bad timing {ai['entry_timing']}")
            return None

        if ai["late_breakout_risk"]:
            print(f"{ticker}: rejected, AI sees late breakout risk")
            return None

        if REQUIRE_RETEST and not ai["retest_confirmed"]:
            print(f"{ticker}: rejected, AI says no retest confirmation")
            return None

        ranking_score = best["score"] + ai["confidence"] + (ai["risk_reward"] * 10)

        if ai["setup_quality"] == "A+":
            ranking_score += 20
        elif ai["setup_quality"] == "A":
            ranking_score += 10

        if ai["entry_timing"] == "IDEAL":
            ranking_score += 15
        elif ai["entry_timing"] == "EARLY":
            ranking_score += 8

        if best.get("retest_confirmed"):
            ranking_score += 10

        if intraday_info.get("approved"):
            ranking_score += 15

        if intraday_info.get("confirmations", 0) >= 3:
            ranking_score += 10

        return {
            "ticker": ticker,
            "setup": best,
            "tech": tech,
            "ai": ai,
            "intraday": intraday_info,
            "ranking_score": ranking_score,
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

    def alert(self, ticker, setup, tech, ai, intraday_info=None, ranking_score=0):
        direction = setup["direction"]
        emoji = "🟢" if direction == "CALL" else "🔴"
        market = self.get_market_bias()
        alert_time = dt.datetime.now(dt.timezone.utc).isoformat()
        intraday_info = intraday_info or {}

        msg = (
            f"{emoji} *A+ {direction} SETUP: {ticker}*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 *Day:* {tech['trading_day']}\n"
            f"💰 *Price:* ${fmt_price(tech['price'])}\n"
            f"⭐ *Rule Score:* {setup['score']}/100\n"
            f"🏅 *Rank Score:* {ranking_score:.1f}\n"
            f"🤖 *AI:* {ai['verdict']} ({ai['confidence']}%)\n"
            f"🏆 *Quality:* {ai['setup_quality']} | *Timing:* {ai['entry_timing']}\n"
            f"🌎 *ETF Bias:* {market['bias']} ({market['bullish_count']} bull / {market['bearish_count']} bear)\n"
            f"📊 *Intraday:* {intraday_info.get('confirmations')}/{intraday_info.get('required_confirmations')} | {intraday_info.get('reason')}\n\n"
            f"🎯 *Entry:* {fmt_price(ai['entry'])}\n"
            f"🛑 *Stop:* {fmt_price(ai['stop'])}\n"
            f"🚀 *Target:* {fmt_price(ai['target'])}\n"
            f"📐 *R/R:* {ai['risk_reward']:.2f}:1\n"
            f"📏 *ATR14:* {fmt_price(tech['atr14'])}\n\n"
            f"📍 *VWAP:* {fmt_price(tech['vwap'])}\n"
            f"📈 *EMA9/21/50:* {fmt_price(tech['ema9'])} / {fmt_price(tech['ema21'])} / {fmt_price(tech['ema50'])}\n"
            f"📊 *DMA20/50/200:* {fmt_price(tech['dma20'])} / {fmt_price(tech['dma50'])} / {fmt_price(tech['dma200'])}\n"
            f"🟦 *ORB H/L:* {fmt_price(tech['orb_high'])} / {fmt_price(tech['orb_low'])}\n"
            f"🌅 *PM H/L:* {fmt_price(tech['premarket_high'])} / {fmt_price(tech['premarket_low'])}\n"
            f"📆 *PD H/L:* {fmt_price(tech['prev_high'])} / {fmt_price(tech['prev_low'])}\n"
            f"📊 *Vol:* {tech['current_volume']} / Avg20 {tech['avg_20_volume']}\n\n"
            f"🔥 *Retest:* {ai['retest_confirmed']}\n"
            f"⚠️ *Late Risk:* {ai['late_breakout_risk']}\n\n"
            f"📝 *AI Reason:* {ai['reason']}\n\n"
            f"🔎 *Rule Reasons:* {', '.join(setup['reasons'])}\n"
            f"🌎 *ETF Details:* {', '.join(market['details'])}"
        )

        self.send_telegram_msg(msg)

        log_alert({
            "timestamp": alert_time,
            "ticker": ticker,
            "direction": direction,
            "score": setup["score"],
            "ranking_score": ranking_score,
            "ai_verdict": ai["verdict"],
            "ai_confidence": ai["confidence"],
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
            "reasons": ", ".join(setup["reasons"])
        })

        if ai["entry"] and ai["stop"] and ai["target"]:
            outcome = track_outcome(
                ticker=ticker,
                direction=direction,
                entry=float(ai["entry"]),
                stop=float(ai["stop"]),
                target=float(ai["target"]),
                alert_time_iso=alert_time,
            )

            if outcome:
                print(
                    f"{ticker}: outcome={outcome['result']} "
                    f"max_gain={outcome['max_gain_pct']}% "
                    f"max_loss={outcome['max_loss_pct']}%"
                )

    async def run(self):
        print("🚀 Stock Technical AI Bot Running")

        while True:
            if not self.is_regular_market_hours() or not self.is_quality_trading_window():
                print("⏸ Outside quality market window | sleeping 600s")
                await asyncio.sleep(600)
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
                self.alert(
                    c["ticker"],
                    c["setup"],
                    c["tech"],
                    c["ai"],
                    c.get("intraday"),
                    c["ranking_score"]
                )
                self.mark_alert(c["ticker"], c["setup"]["direction"])

            print(
                f"✅ Scan complete | candidates={len(candidates)} | "
                f"sent={len(selected)} | sleeping {SCAN_INTERVAL_SEC}s"
            )
            await asyncio.sleep(SCAN_INTERVAL_SEC)
