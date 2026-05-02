from config import *
from polygon import RESTClient

import datetime as dt
import time
import requests
from typing import List

from bot_utils import safe_float, pct_diff


client = RESTClient(POLYGON_API_KEY)


class StockTechnicalBase:
    def __init__(self, tickers: List[str]):
        self.base_tickers = tickers
        self.tickers = tickers
        self.state = {t: {"last_alert_time": {}} for t in tickers}
        self.tech_cache = {}
        self.tech_cache_time = {}
        self.market_bias_cache = None
        self.market_bias_cache_time = 0

    def get_auto_watchlist(self) -> List[str]:
        if not USE_AUTO_WATCHLIST:
            return self.base_tickers

        url = (
            "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
            f"?apiKey={POLYGON_API_KEY}"
        )

        try:
            r = requests.get(url, timeout=20)
            data = r.json()
            movers = []

            for item in data.get("tickers", []):
                ticker = item.get("ticker")
                day = item.get("day", {})
                last_trade = item.get("lastTrade", {})

                change_pct = abs(safe_float(item.get("todaysChangePerc")))
                volume = safe_float(day.get("v"))
                price = safe_float(last_trade.get("p"))

                if price < MIN_STOCK_PRICE:
                    continue

                if ticker and volume >= MIN_AUTO_VOLUME and change_pct >= MIN_AUTO_CHANGE_PCT:
                    movers.append((ticker, change_pct, volume, price))

            movers.sort(key=lambda x: (x[1], x[2], x[3]), reverse=True)

            auto = [x[0] for x in movers[:AUTO_WATCHLIST_LIMIT]]
            final = list(dict.fromkeys(self.base_tickers + auto))

            for t in final:
                if t not in self.state:
                    self.state[t] = {"last_alert_time": {}}

            print(f"📌 Auto watchlist size: {len(final)}")
            return final

        except Exception as e:
            print(f"Auto-watchlist error: {e}")
            return self.base_tickers

    def cooldown_active(self, ticker, direction):
        last = self.state[ticker]["last_alert_time"].get(direction)
        return last and time.time() - last < ALERT_COOLDOWN_SEC

    def is_regular_market_hours(self):
        now = dt.datetime.now(MARKET_TZ)
        return dt.time(9, 30) <= now.time() <= dt.time(16, 0)

    def mark_alert(self, ticker, direction):
        self.state[ticker]["last_alert_time"][direction] = time.time()

    def sma(self, values, length):
        if len(values) < length:
            return None
        return sum(values[-length:]) / length

    def ema(self, values, length):
        if len(values) < length:
            return None

        k = 2 / (length + 1)
        ema_val = sum(values[:length]) / length

        for price in values[length:]:
            ema_val = price * k + ema_val * (1 - k)

        return ema_val

    def atr(self, daily_bars, period=14):
        if len(daily_bars) < period + 1:
            return None

        trs = []

        for i in range(1, len(daily_bars)):
            high = safe_float(daily_bars[i].high)
            low = safe_float(daily_bars[i].low)
            prev_close = safe_float(daily_bars[i - 1].close)

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            trs.append(tr)

        return sum(trs[-period:]) / period if len(trs) >= period else None

    def aggregate_bars(self, bars, group_size):
        grouped = []

        for i in range(0, len(bars), group_size):
            chunk = bars[i:i + group_size]

            if len(chunk) < group_size:
                continue

            grouped.append({
                "open": safe_float(chunk[0].open),
                "high": max(safe_float(x.high) for x in chunk),
                "low": min(safe_float(x.low) for x in chunk),
                "close": safe_float(chunk[-1].close),
                "volume": sum(safe_float(x.volume) for x in chunk),
            })

        return grouped

    def timeframe_trend(self, bars):
        if len(bars) < 21:
            return "NEUTRAL"

        closes = [safe_float(x["close"]) for x in bars]
        ema9 = self.ema(closes, 9)
        ema21 = self.ema(closes, 21)

        if ema9 is None or ema21 is None:
            return "NEUTRAL"

        if closes[-1] > ema9 > ema21:
            return "BULLISH"

        if closes[-1] < ema9 < ema21:
            return "BEARISH"

        return "NEUTRAL"

    def is_quality_trading_window(self):
        now = dt.datetime.now(MARKET_TZ).time()

        for start_s, end_s in QUALITY_WINDOWS:
            start_h, start_m = map(int, start_s.split(":"))
            end_h, end_m = map(int, end_s.split(":"))

            if dt.time(start_h, start_m) <= now <= dt.time(end_h, end_m):
                return True

        return False

    def call_above_pm_or_pd_high(self, tech):
        price = tech["price"]
        pm_high = tech.get("premarket_high")
        pd_high = tech.get("prev_high")

        return (
            (pm_high is not None and price > pm_high) or
            (pd_high is not None and price > pd_high)
        )

    def put_below_pm_or_pd_low(self, tech):
        price = tech["price"]
        pm_low = tech.get("premarket_low")
        pd_low = tech.get("prev_low")

        return (
            (pm_low is not None and price < pm_low) or
            (pd_low is not None and price < pd_low)
        )

    def get_sector_etf(self, ticker):
        return SECTOR_ETF_MAP.get(ticker)

    def get_sector_confirmation(self, ticker, direction):
        etf = self.get_sector_etf(ticker)

        if not etf:
            return "NO_SECTOR_ETF", "no sector ETF mapping"

        tech = self.get_technical_context(etf)

        if not tech:
            return "UNKNOWN", f"{etf} unavailable"

        price = tech["price"]

        bullish = (
            tech.get("vwap") and price > tech["vwap"] and
            tech.get("ema9") and tech.get("ema21") and tech["ema9"] > tech["ema21"]
        )

        bearish = (
            tech.get("vwap") and price < tech["vwap"] and
            tech.get("ema9") and tech.get("ema21") and tech["ema9"] < tech["ema21"]
        )

        if direction == "CALL" and bullish:
            return "CONFIRMED", f"{etf} confirms bullish sector bias"

        if direction == "PUT" and bearish:
            return "CONFIRMED", f"{etf} confirms bearish sector bias"

        return "CONFLICT", f"{etf} does not confirm {direction}"
        
    def get_latest_trading_day(self):
        now = dt.datetime.now(MARKET_TZ)
        day = now.date()

        while day.weekday() >= 5:
            day -= dt.timedelta(days=1)

        if now.time() < dt.time(9, 45):
            day -= dt.timedelta(days=1)
            while day.weekday() >= 5:
                day -= dt.timedelta(days=1)

        return day

    def get_aggs(self, ticker, multiplier, timespan, start, end):
        try:
            return list(
                client.list_aggs(
                    ticker=ticker,
                    multiplier=multiplier,
                    timespan=timespan,
                    from_=str(start),
                    to=str(end),
                    adjusted=True,
                    sort="asc",
                    limit=50000,
                )
            )
        except Exception as e:
            print(f"{ticker}: aggregate error {timespan}: {e}")
            return []

    def get_technical_context(self, ticker):
        now_ts = time.time()

        if ticker in self.tech_cache and now_ts - self.tech_cache_time[ticker] < 60:
            return self.tech_cache[ticker]

        day = self.get_latest_trading_day()

        daily = self.get_aggs(ticker, 1, "day", day - dt.timedelta(days=330), day)
        minute = self.get_aggs(ticker, 1, "minute", day, day)

        if not daily:
            print(f"{ticker}: no daily data")
            return None

        if not minute:
            print(f"{ticker}: no minute data for {day}")
            return None

        daily_closes = [safe_float(x.close) for x in daily if x.close is not None]

        dma20 = self.sma(daily_closes, DMA_SHORT)
        dma50 = self.sma(daily_closes, DMA_FAST)
        dma200 = self.sma(daily_closes, DMA_SLOW)
        atr14 = self.atr(daily, ATR_PERIOD)

        prev = daily[-2] if len(daily) >= 2 else None
        prev_high = safe_float(prev.high) if prev else None
        prev_low = safe_float(prev.low) if prev else None

        regular = []
        premarket = []

        for bar in minute:
            ts = dt.datetime.fromtimestamp(
                bar.timestamp / 1000,
                tz=dt.timezone.utc,
            ).astimezone(MARKET_TZ)

            t = ts.time()

            if dt.time(4, 0) <= t < dt.time(9, 30):
                premarket.append(bar)

            if dt.time(9, 30) <= t <= dt.time(16, 0):
                regular.append(bar)

        if not regular:
            print(
                f"{ticker}: no regular-session bars for {day}. "
                f"Current ET={dt.datetime.now(MARKET_TZ).strftime('%H:%M:%S')}"
            )
            return None

        closes = [safe_float(x.close) for x in regular]
        volumes = [safe_float(x.volume) for x in regular]

        ema9 = self.ema(closes, EMA_FAST)
        ema21 = self.ema(closes, EMA_SLOW)
        ema50 = self.ema(closes, EMA_TREND)

        avg_20_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else None
        current_volume = volumes[-1] if volumes else None

        total_pv = 0.0
        total_vol = 0.0

        for bar in regular:
            typical = (
                safe_float(bar.high)
                + safe_float(bar.low)
                + safe_float(bar.close)
            ) / 3

            total_pv += typical * safe_float(bar.volume)
            total_vol += safe_float(bar.volume)

        vwap = total_pv / total_vol if total_vol > 0 else None

        orb_bars = regular[:ORB_MINUTES]
        orb_high = max([safe_float(x.high) for x in orb_bars]) if orb_bars else None
        orb_low = min([safe_float(x.low) for x in orb_bars]) if orb_bars else None

        pm_high = max([safe_float(x.high) for x in premarket]) if premarket else None
        pm_low = min([safe_float(x.low) for x in premarket]) if premarket else None

        last_20 = regular[-20:] if len(regular) >= 20 else regular
        recent_high = max([safe_float(x.high) for x in last_20]) if last_20 else None
        recent_low = min([safe_float(x.low) for x in last_20]) if last_20 else None

        prev_10 = regular[-11:-1] if len(regular) >= 11 else regular[:-1]
        previous_recent_high = max([safe_float(x.high) for x in prev_10]) if prev_10 else None
        previous_recent_low = min([safe_float(x.low) for x in prev_10]) if prev_10 else None

        bars_5m = self.aggregate_bars(regular, 5)
        bars_15m = self.aggregate_bars(regular, 15)

        trend_5m = self.timeframe_trend(bars_5m)
        trend_15m = self.timeframe_trend(bars_15m)

        price = safe_float(regular[-1].close)

        tech = {
            "ticker": ticker,
            "trading_day": str(day),
            "price": price,
            "vwap": vwap,
            "ema9": ema9,
            "ema21": ema21,
            "ema50": ema50,
            "dma20": dma20,
            "dma50": dma50,
            "dma200": dma200,
            "atr14": atr14,
            "trend_5m": trend_5m,
            "trend_15m": trend_15m,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "premarket_high": pm_high,
            "premarket_low": pm_low,
            "prev_high": prev_high,
            "prev_low": prev_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "previous_recent_high": previous_recent_high,
            "previous_recent_low": previous_recent_low,
            "current_volume": current_volume,
            "avg_20_volume": avg_20_volume,
            "last_5_closes": [safe_float(x.close) for x in regular[-5:]],
            "last_5_lows": [safe_float(x.low) for x in regular[-5:]],
            "last_5_highs": [safe_float(x.high) for x in regular[-5:]],
        }

        self.tech_cache[ticker] = tech
        self.tech_cache_time[ticker] = now_ts

        return tech

    def is_near_level(self, price, level, tolerance_pct):
        if price is None or level is None:
            return False

        diff = abs(pct_diff(price, level))
        return diff is not None and diff <= tolerance_pct

    def near_level(self, price, level, buffer_pct):
        return self.is_near_level(price, level, buffer_pct)

    def call_above_pm_or_pd_high(self, tech):
        price = tech["price"]
        pm_high = tech.get("premarket_high")
        pd_high = tech.get("prev_high")

        above_pm = pm_high is not None and price > pm_high
        above_pd = pd_high is not None and price > pd_high

        return above_pm or above_pd

    def put_below_pm_or_pd_low(self, tech):
        price = tech["price"]
        pm_low = tech.get("premarket_low")
        pd_low = tech.get("prev_low")

        below_pm = pm_low is not None and price < pm_low
        below_pd = pd_low is not None and price < pd_low

        return below_pm or below_pd
        
    def detect_call_retest(self, tech):
        price = tech["price"]
        lows = tech.get("last_5_lows", [])

        levels = [
            ("ORB high", tech.get("orb_high")),
            ("premarket high", tech.get("premarket_high")),
            ("previous day high", tech.get("prev_high")),
            ("VWAP", tech.get("vwap")),
            ("EMA21", tech.get("ema21")),
        ]

        for name, level in levels:
            if level is None:
                continue

            touched = any(self.is_near_level(low, level, RETEST_TOLERANCE_PCT) for low in lows)
            reclaimed = price > level

            if touched and reclaimed:
                return True, f"retest confirmed at {name}"

        return False, "no clean bullish retest"

    def detect_put_retest(self, tech):
        price = tech["price"]
        highs = tech.get("last_5_highs", [])

        levels = [
            ("ORB low", tech.get("orb_low")),
            ("premarket low", tech.get("premarket_low")),
            ("previous day low", tech.get("prev_low")),
            ("VWAP", tech.get("vwap")),
            ("EMA21", tech.get("ema21")),
        ]

        for name, level in levels:
            if level is None:
                continue

            touched = any(self.is_near_level(high, level, RETEST_TOLERANCE_PCT) for high in highs)
            rejected = price < level

            if touched and rejected:
                return True, f"retest confirmed at {name}"

        return False, "no clean bearish retest"

    def detect_late_breakout(self, direction, tech):
        price = tech["price"]
        vwap_ext = abs(pct_diff(price, tech.get("vwap"))) if tech.get("vwap") else 0

        if vwap_ext > MAX_EXTENSION_FROM_VWAP_PCT:
            return True, f"price extended {vwap_ext:.2f}% from VWAP"

        if direction == "CALL":
            levels = [tech.get("orb_high"), tech.get("premarket_high"), tech.get("prev_high")]
            label = "breakout"
        else:
            levels = [tech.get("orb_low"), tech.get("premarket_low"), tech.get("prev_low")]
            label = "breakdown"

        extension = max([abs(pct_diff(price, x)) for x in levels if x] or [0])

        if extension > MAX_EXTENSION_FROM_ORB_PCT:
            return True, f"price extended {extension:.2f}% beyond {label} level"

        return False, "not extended"

    def failed_call_breakout(self, tech):
        closes = tech.get("last_5_closes", [])
        levels = [
            tech.get("orb_high"),
            tech.get("premarket_high"),
            tech.get("prev_high"),
        ]
        levels = [x for x in levels if x is not None]

        if not closes or not levels:
            return False

        for level in levels:
            broke_above = max(closes) > level
            now_below = closes[-1] < level
            if broke_above and now_below:
                return True

        return False

    def failed_put_breakdown(self, tech):
        closes = tech.get("last_5_closes", [])
        levels = [
            tech.get("orb_low"),
            tech.get("premarket_low"),
            tech.get("prev_low"),
        ]
        levels = [x for x in levels if x is not None]

        if not closes or not levels:
            return False

        for level in levels:
            broke_below = min(closes) < level
            now_above = closes[-1] > level
            if broke_below and now_above:
                return True

        return False

    def has_volume_spike(self, tech):
        if not tech.get("current_volume") or not tech.get("avg_20_volume"):
            return False

        return tech["current_volume"] >= tech["avg_20_volume"] * VOLUME_SPIKE_MULTIPLIER

    def relative_strength_vs_spy(self, tech):
        if tech.get("ticker") == "SPY":
            return "NEUTRAL"

        spy = self.get_technical_context("SPY")
        if not spy:
            return "NEUTRAL"

        stock_move = pct_diff(tech["price"], tech["vwap"])
        spy_move = pct_diff(spy["price"], spy["vwap"])

        if stock_move is None or spy_move is None:
            return "NEUTRAL"

        if stock_move > spy_move:
            return "STRONG"

        if stock_move < spy_move:
            return "WEAK"

        return "NEUTRAL"

    def continuation_confirmed(self, direction, tech):
        closes = tech.get("last_5_closes", [])

        if len(closes) < 3:
            return False

        if direction == "CALL":
            return closes[-1] > closes[-2] > closes[-3]

        if direction == "PUT":
            return closes[-1] < closes[-2] < closes[-3]

        return False

    def get_market_bias(self):
        now_ts = time.time()

        if self.market_bias_cache and now_ts - self.market_bias_cache_time < 60:
            return self.market_bias_cache

        bullish = 0
        bearish = 0
        details = []

        for ticker in MARKET_BIAS_TICKERS:
            tech = self.get_technical_context(ticker)

            if not tech:
                details.append(f"{ticker}: unavailable")
                continue

            price = tech["price"]
            bull = 0
            bear = 0

            if tech["vwap"]:
                if price > tech["vwap"]:
                    bull += 1
                elif price < tech["vwap"]:
                    bear += 1

            if tech["ema9"] and tech["ema21"]:
                if tech["ema9"] > tech["ema21"]:
                    bull += 1
                elif tech["ema9"] < tech["ema21"]:
                    bear += 1

            if tech["ema21"] and tech["ema50"]:
                if tech["ema21"] > tech["ema50"]:
                    bull += 1
                elif tech["ema21"] < tech["ema50"]:
                    bear += 1

            if tech["orb_high"] and price > tech["orb_high"]:
                bull += 1

            if tech["orb_low"] and price < tech["orb_low"]:
                bear += 1

            if tech["prev_high"] and price > tech["prev_high"]:
                bull += 1

            if tech["prev_low"] and price < tech["prev_low"]:
                bear += 1

            if bull > bear:
                bullish += 1
                details.append(f"{ticker}: bullish")
            elif bear > bull:
                bearish += 1
                details.append(f"{ticker}: bearish")
            else:
                details.append(f"{ticker}: neutral")

        if bullish >= bearish + 1:
            bias = "BULLISH"
        elif bearish >= bullish + 1:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        result = {
            "bias": bias,
            "bullish_count": bullish,
            "bearish_count": bearish,
            "details": details,
        }

        self.market_bias_cache = result
        self.market_bias_cache_time = now_ts

        return result

    def score_call_setup(self, tech):
        price = tech["price"]
        score = 0
        reasons = []

        if tech["vwap"] and price > tech["vwap"]:
            score += 15
            reasons.append("price above VWAP")

        if tech["ema9"] and tech["ema21"] and tech["ema9"] > tech["ema21"]:
            score += 15
            reasons.append("EMA9 above EMA21")

        if tech["ema21"] and tech["ema50"] and tech["ema21"] > tech["ema50"]:
            score += 15
            reasons.append("EMA21 above EMA50")

        if tech["dma20"] and price > tech["dma20"]:
            score += 10
            reasons.append("price above 20 DMA")

        if tech["dma50"] and price > tech["dma50"]:
            score += 10
            reasons.append("price above 50 DMA")

        if tech["dma200"] and price > tech["dma200"]:
            score += 10
            reasons.append("price above 200 DMA")

        if CONFIRM_5M_15M:
            if tech["trend_5m"] == "BULLISH" and tech["trend_15m"] == "BULLISH":
                score += TIMEFRAME_CONFIRM_WEIGHT
                reasons.append("5m and 15m bullish trend aligned")
            else:
                score -= TIMEFRAME_CONFIRM_WEIGHT
                reasons.append("5m/15m trend not aligned bullish")

        resistance_levels = [
            tech.get("prev_high"),
            tech.get("premarket_high"),
            tech.get("recent_high"),
        ]

        if any(
            self.near_level(price, lvl, SUPPORT_RESISTANCE_BUFFER_PCT) and price < lvl
            for lvl in resistance_levels
            if lvl
        ):
            score -= SR_REJECTION_WEIGHT
            reasons.append("CALL rejected: price too close below resistance")

        if self.failed_call_breakout(tech):
            score -= FAILED_BREAKOUT_WEIGHT
            reasons.append("failed bullish breakout detected")

        breakouts = []

        if tech["orb_high"] and price > tech["orb_high"]:
            breakouts.append("15m ORB high")

        if tech["premarket_high"] and price > tech["premarket_high"]:
            breakouts.append("premarket high")

        if tech["prev_high"] and price > tech["prev_high"]:
            breakouts.append("previous day high")

        if breakouts:
            score += 25
            reasons.append("breakout above " + ", ".join(breakouts))

        retest_ok, retest_reason = self.detect_call_retest(tech)
        late, late_reason = self.detect_late_breakout("CALL", tech)

        if retest_ok:
            score += 10
            reasons.append(retest_reason)

        if late:
            score -= 20
            reasons.append("late breakout risk: " + late_reason)

        if REQUIRE_RETEST and not retest_ok:
            score -= 15
            reasons.append("A+ filter failed: retest not confirmed")

        if self.has_volume_spike(tech):
            score += VOLUME_SPIKE_WEIGHT
            reasons.append("volume spike confirms momentum")

        rs = self.relative_strength_vs_spy(tech)
        if rs == "STRONG":
            score += RELATIVE_STRENGTH_WEIGHT
            reasons.append("relative strength vs SPY")
        elif rs == "WEAK":
            score -= RELATIVE_STRENGTH_WEIGHT
            reasons.append("weak relative strength vs SPY")

        if self.continuation_confirmed("CALL", tech):
            score += CONTINUATION_WEIGHT
            reasons.append("bullish continuation confirmed by last candles")

        market = self.get_market_bias()

        if market["bias"] == "BULLISH":
            score += MARKET_BIAS_WEIGHT
            reasons.append("market bias bullish: " + ", ".join(market["details"]))

        elif market["bias"] == "BEARISH":
            score -= MARKET_BIAS_WEIGHT
            reasons.append("market bias against CALLs: " + ", ".join(market["details"]))

        elif REQUIRE_MARKET_BIAS:
            score -= MARKET_BIAS_WEIGHT
            reasons.append("market bias neutral, CALL deprioritized")

        if self.call_above_pm_or_pd_high(tech):
            score += A_PLUS_BREAKOUT_BONUS
            reasons.append("A+ CALL condition met: price above premarket high or previous day high")
        elif REQUIRE_PM_OR_PD_BREAK_FOR_A_PLUS:
            score -= A_PLUS_BREAKOUT_PENALTY
            reasons.append("A+ CALL blocked: price not above premarket high or previous day high")

        if self.call_above_pm_or_pd_high(tech):
            score += A_PLUS_BREAKOUT_BONUS
            reasons.append("A+ CALL condition met: price above premarket high or previous day high")
        elif REQUIRE_PM_OR_PD_BREAK_FOR_A_PLUS:
            score -= A_PLUS_BREAKOUT_PENALTY
            reasons.append("A+ CALL blocked: price not above premarket high or previous day high")

        sector_status, sector_reason = self.get_sector_confirmation(tech["ticker"], "CALL")

        if sector_status == "CONFIRMED":
            score += SECTOR_ETF_WEIGHT
            reasons.append(sector_reason)
        elif sector_status == "CONFLICT":
            score -= SECTOR_ETF_WEIGHT
            reasons.append(sector_reason)
        elif REQUIRE_SECTOR_CONFIRMATION:
            score -= SECTOR_ETF_WEIGHT
            reasons.append("sector ETF confirmation missing")
                        
        return {
            "direction": "CALL",
            "score": max(score, 0),
            "reasons": reasons,
            "retest_confirmed": retest_ok,
            "late_breakout_risk": late,
            "late_reason": late_reason,
        }

    def score_put_setup(self, tech):
        price = tech["price"]
        score = 0
        reasons = []

        if tech["vwap"] and price < tech["vwap"]:
            score += 15
            reasons.append("price below VWAP")

        if tech["ema9"] and tech["ema21"] and tech["ema9"] < tech["ema21"]:
            score += 15
            reasons.append("EMA9 below EMA21")

        if tech["ema21"] and tech["ema50"] and tech["ema21"] < tech["ema50"]:
            score += 15
            reasons.append("EMA21 below EMA50")

        if tech["dma20"] and price < tech["dma20"]:
            score += 10
            reasons.append("price below 20 DMA")

        if tech["dma50"] and price < tech["dma50"]:
            score += 10
            reasons.append("price below 50 DMA")

        if tech["dma200"] and price < tech["dma200"]:
            score += 10
            reasons.append("price below 200 DMA")

        if CONFIRM_5M_15M:
            if tech["trend_5m"] == "BEARISH" and tech["trend_15m"] == "BEARISH":
                score += TIMEFRAME_CONFIRM_WEIGHT
                reasons.append("5m and 15m bearish trend aligned")
            else:
                score -= TIMEFRAME_CONFIRM_WEIGHT
                reasons.append("5m/15m trend not aligned bearish")

        support_levels = [
            tech.get("prev_low"),
            tech.get("premarket_low"),
            tech.get("recent_low"),
        ]

        if any(
            self.near_level(price, lvl, SUPPORT_RESISTANCE_BUFFER_PCT) and price > lvl
            for lvl in support_levels
            if lvl
        ):
            score -= SR_REJECTION_WEIGHT
            reasons.append("PUT rejected: price too close above support")

        if self.failed_put_breakdown(tech):
            score -= FAILED_BREAKOUT_WEIGHT
            reasons.append("failed bearish breakdown detected")

        breakdowns = []

        if tech["orb_low"] and price < tech["orb_low"]:
            breakdowns.append("15m ORB low")

        if tech["premarket_low"] and price < tech["premarket_low"]:
            breakdowns.append("premarket low")

        if tech["prev_low"] and price < tech["prev_low"]:
            breakdowns.append("previous day low")

        if breakdowns:
            score += 25
            reasons.append("breakdown below " + ", ".join(breakdowns))

        retest_ok, retest_reason = self.detect_put_retest(tech)
        late, late_reason = self.detect_late_breakout("PUT", tech)

        if retest_ok:
            score += 10
            reasons.append(retest_reason)

        if late:
            score -= 20
            reasons.append("late breakdown risk: " + late_reason)

        if REQUIRE_RETEST and not retest_ok:
            score -= 15
            reasons.append("A+ filter failed: retest not confirmed")

        if self.has_volume_spike(tech):
            score += VOLUME_SPIKE_WEIGHT
            reasons.append("volume spike confirms momentum")

        rs = self.relative_strength_vs_spy(tech)
        if rs == "WEAK":
            score += RELATIVE_STRENGTH_WEIGHT
            reasons.append("relative weakness vs SPY")
        elif rs == "STRONG":
            score -= RELATIVE_STRENGTH_WEIGHT
            reasons.append("too strong vs SPY for PUT")

        if self.continuation_confirmed("PUT", tech):
            score += CONTINUATION_WEIGHT
            reasons.append("bearish continuation confirmed by last candles")

        market = self.get_market_bias()

        if market["bias"] == "BEARISH":
            score += MARKET_BIAS_WEIGHT
            reasons.append("market bias bearish: " + ", ".join(market["details"]))

        elif market["bias"] == "BULLISH":
            score -= MARKET_BIAS_WEIGHT
            reasons.append("market bias against PUTs: " + ", ".join(market["details"]))

        elif REQUIRE_MARKET_BIAS:
            score -= MARKET_BIAS_WEIGHT
            reasons.append("market bias neutral, PUT deprioritized")

        if self.put_below_pm_or_pd_low(tech):
            score += A_PLUS_BREAKOUT_BONUS
            reasons.append("A+ PUT condition met: price below premarket low or previous day low")
        elif REQUIRE_PM_OR_PD_BREAK_FOR_A_PLUS:
            score -= A_PLUS_BREAKOUT_PENALTY
            reasons.append("A+ PUT blocked: price not below premarket low or previous day low")

        if self.put_below_pm_or_pd_low(tech):
            score += A_PLUS_BREAKOUT_BONUS
            reasons.append("A+ PUT condition met: price below premarket low or previous day low")
        elif REQUIRE_PM_OR_PD_BREAK_FOR_A_PLUS:
            score -= A_PLUS_BREAKOUT_PENALTY
            reasons.append("A+ PUT blocked: price not below premarket low or previous day low")

        sector_status, sector_reason = self.get_sector_confirmation(tech["ticker"], "PUT")

        if sector_status == "CONFIRMED":
            score += SECTOR_ETF_WEIGHT
            reasons.append(sector_reason)
        elif sector_status == "CONFLICT":
            score -= SECTOR_ETF_WEIGHT
            reasons.append(sector_reason)
        elif REQUIRE_SECTOR_CONFIRMATION:
            score -= SECTOR_ETF_WEIGHT
            reasons.append("sector ETF confirmation missing")
                        
        return {
            "direction": "PUT",
            "score": max(score, 0),
            "reasons": reasons,
            "retest_confirmed": retest_ok,
            "late_breakout_risk": late,
            "late_reason": late_reason,
        }
