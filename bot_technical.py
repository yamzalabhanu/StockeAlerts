from config import *
from polygon import RESTClient

import datetime as dt
import time
import requests
from typing import Any, Dict, List, Optional, Union

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

    def _parse_watchlist_day(
        self, day: Optional[Union[str, dt.date, dt.datetime]] = None
    ) -> Optional[dt.date]:
        if day is None:
            configured_day = globals().get("AUTO_WATCHLIST_DATE", "")
            day = configured_day or None

        if day is None:
            return None

        if isinstance(day, dt.datetime):
            return day.date()

        if isinstance(day, dt.date):
            return day

        if isinstance(day, str):
            raw = day.strip()
            if not raw:
                return None
            return dt.date.fromisoformat(raw)

        raise TypeError(
            "watchlist day must be a YYYY-MM-DD string, date, datetime, or None"
        )

    def _merge_auto_watchlist(self, auto: List[str], label: str) -> List[str]:
        final = list(dict.fromkeys(self.base_tickers + auto))

        for t in final:
            if t not in self.state:
                self.state[t] = {"last_alert_time": {}}

        print(f"📌 Auto watchlist size: {len(final)} ({label})")
        return final

    def _request_polygon_json(self, url: str, params=None):
        params = dict(params or {})
        if "apiKey" not in params and "apiKey=" not in url:
            params["apiKey"] = POLYGON_API_KEY

        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def _previous_trading_day(self, day: dt.date) -> dt.date:
        previous = day - dt.timedelta(days=1)
        while previous.weekday() >= 5:
            previous -= dt.timedelta(days=1)
        return previous

    def _get_grouped_daily_aggs(self, day: dt.date) -> list:
        url = (
            "https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/"
            f"{day.isoformat()}"
        )
        data = self._request_polygon_json(url, params={"adjusted": "true"})
        return data.get("results", []) or []

    def _get_previous_closes(self, day: dt.date) -> Dict[str, float]:
        try:
            previous_day = self._previous_trading_day(day)
            return {
                item.get("T"): safe_float(item.get("c"))
                for item in self._get_grouped_daily_aggs(previous_day)
                if item.get("T") and safe_float(item.get("c")) > 0
            }
        except Exception as e:
            print(f"Previous close lookup skipped for {day}: {e}")
            return {}

    def _empty_extended_metrics(self) -> Dict[str, Any]:
        return {
            "premarket_volume": 0.0,
            "premarket_change_pct": 0.0,
            "afterhours_volume": 0.0,
            "afterhours_change_pct": 0.0,
            "extended_volume": 0.0,
            "extended_change_pct": 0.0,
        }

    def _get_extended_hours_metrics(
        self, ticker: str, day: dt.date, prev_close: float = 0.0
    ) -> Dict[str, Any]:
        """Return Polygon pre-market/after-hours volume and move for one ticker/day."""
        if not AUTO_WATCHLIST_USE_EXTENDED_HOURS:
            return self._empty_extended_metrics()

        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/minute/"
            f"{day.isoformat()}/{day.isoformat()}"
        )
        data = self._request_polygon_json(
            url,
            params={"adjusted": "true", "sort": "asc", "limit": 50000},
        )

        sessions = {
            "premarket": {"volume": 0.0, "close": None},
            "afterhours": {"volume": 0.0, "close": None},
        }

        for bar in data.get("results", []) or []:
            timestamp = safe_float(bar.get("t"))
            if timestamp <= 0:
                continue

            bar_time = (
                dt.datetime.fromtimestamp(timestamp / 1000, dt.timezone.utc)
                .astimezone(MARKET_TZ)
                .time()
            )
            session = None
            if dt.time(4, 0) <= bar_time < dt.time(9, 30):
                session = "premarket"
            elif dt.time(16, 0) <= bar_time <= dt.time(20, 0):
                session = "afterhours"

            if not session:
                continue

            sessions[session]["volume"] += safe_float(bar.get("v"))
            sessions[session]["close"] = safe_float(bar.get("c"))

        metrics = self._empty_extended_metrics()
        for session in ("premarket", "afterhours"):
            volume = sessions[session]["volume"]
            close_price = safe_float(sessions[session]["close"])
            change_pct = (
                abs(pct_diff(close_price, prev_close) or 0) if prev_close else 0.0
            )
            metrics[f"{session}_volume"] = volume
            metrics[f"{session}_change_pct"] = change_pct

        metrics["extended_volume"] = max(
            metrics["premarket_volume"], metrics["afterhours_volume"]
        )
        metrics["extended_change_pct"] = max(
            metrics["premarket_change_pct"], metrics["afterhours_change_pct"]
        )
        return metrics

    def _get_options_activity_metrics(self, ticker: str) -> Dict[str, Any]:
        """Summarize Polygon option snapshot volume/OI for watchlist ranking."""
        metrics = {"option_volume": 0, "option_open_interest": 0, "option_contracts": 0}
        if not AUTO_WATCHLIST_USE_OPTIONS:
            return metrics

        for contract_type in ("call", "put"):
            url = f"https://api.polygon.io/v3/snapshot/options/{ticker}"
            try:
                data = self._request_polygon_json(
                    url, params={"contract_type": contract_type, "limit": 250}
                )
            except Exception as e:
                print(
                    f"{contract_type.title()} option metrics skipped for {ticker}: {e}"
                )
                continue

            for item in data.get("results", []) or []:
                day = item.get("day", {}) or {}
                details = item.get("details", {}) or {}
                volume = safe_float(
                    day.get("volume")
                    or day.get("v")
                    or item.get("volume")
                    or item.get("day_volume")
                    or item.get("total_volume")
                )
                open_interest = safe_float(
                    item.get("open_interest")
                    or item.get("openInterest")
                    or item.get("oi")
                    or details.get("open_interest")
                    or details.get("openInterest")
                    or details.get("oi")
                )
                metrics["option_volume"] += int(volume)
                metrics["option_open_interest"] += int(open_interest)
                metrics["option_contracts"] += 1

        return metrics

    def _rank_watchlist_candidates(
        self, candidates: List[Dict[str, Any]], label: str
    ) -> List[str]:
        for index, candidate in enumerate(candidates):
            ticker = candidate["ticker"]

            if index < AUTO_WATCHLIST_EXTENDED_CANDIDATE_LIMIT:
                try:
                    candidate.update(
                        self._get_extended_hours_metrics(
                            ticker,
                            candidate["day"],
                            candidate.get("prev_close", 0.0),
                        )
                    )
                except Exception as e:
                    print(f"Extended-hours watchlist metrics skipped for {ticker}: {e}")

            if index < AUTO_WATCHLIST_OPTIONS_CANDIDATE_LIMIT:
                try:
                    candidate.update(self._get_options_activity_metrics(ticker))
                except Exception as e:
                    print(f"Options watchlist metrics skipped for {ticker}: {e}")

            daily_score = max(
                safe_float(candidate.get("daily_change_pct"))
                / max(MIN_AUTO_CHANGE_PCT, 0.01),
                safe_float(candidate.get("daily_volume")) / max(MIN_AUTO_VOLUME, 1),
            )
            extended_score = max(
                safe_float(candidate.get("extended_change_pct"))
                / max(MIN_EXTENDED_HOURS_CHANGE_PCT, 0.01),
                safe_float(candidate.get("extended_volume"))
                / max(MIN_EXTENDED_HOURS_VOLUME, 1),
            )
            option_score = max(
                safe_float(candidate.get("option_volume"))
                / max(MIN_AUTO_OPTION_VOLUME, 1),
                safe_float(candidate.get("option_open_interest"))
                / max(MIN_AUTO_OPTION_OPEN_INTEREST, 1),
            )

            candidate["watchlist_score"] = (
                daily_score + (extended_score * 1.25) + (option_score * 1.5)
            )
            candidate["qualified"] = (
                (
                    safe_float(candidate.get("daily_volume")) >= MIN_AUTO_VOLUME
                    and safe_float(candidate.get("daily_change_pct"))
                    >= MIN_AUTO_CHANGE_PCT
                )
                or (
                    safe_float(candidate.get("extended_volume"))
                    >= MIN_EXTENDED_HOURS_VOLUME
                    and safe_float(candidate.get("extended_change_pct"))
                    >= MIN_EXTENDED_HOURS_CHANGE_PCT
                )
                or (
                    safe_float(candidate.get("option_volume")) >= MIN_AUTO_OPTION_VOLUME
                    and safe_float(candidate.get("option_open_interest"))
                    >= MIN_AUTO_OPTION_OPEN_INTEREST
                )
            )

        movers = [candidate for candidate in candidates if candidate.get("qualified")]
        movers.sort(
            key=lambda x: (
                safe_float(x.get("watchlist_score")),
                safe_float(x.get("extended_volume")),
                safe_float(x.get("option_volume")),
                safe_float(x.get("daily_volume")),
                safe_float(x.get("price")),
            ),
            reverse=True,
        )

        auto = [x["ticker"] for x in movers[:AUTO_WATCHLIST_LIMIT]]
        return self._merge_auto_watchlist(auto, label)

    def get_active_tickers_for_day(self, day: Union[str, dt.date, dt.datetime]) -> set:
        parsed_day = self._parse_watchlist_day(day)
        if parsed_day is None:
            return set()

        url = "https://api.polygon.io/v3/reference/tickers"
        params = {
            "market": "stocks",
            "locale": "us",
            "active": "true",
            "date": parsed_day.isoformat(),
            "limit": 1000,
            "sort": "ticker",
        }

        tickers = set()
        while url:
            data = self._request_polygon_json(url, params=params)
            for item in data.get("results", []):
                ticker = item.get("ticker")
                if ticker:
                    tickers.add(ticker)

            url = data.get("next_url")
            params = None

        return tickers

    def get_historical_auto_watchlist(
        self, day: Union[str, dt.date, dt.datetime]
    ) -> List[str]:
        parsed_day = self._parse_watchlist_day(day)
        if parsed_day is None:
            return self.base_tickers

        active_tickers = self.get_active_tickers_for_day(parsed_day)
        grouped_results = self._get_grouped_daily_aggs(parsed_day)
        previous_closes = self._get_previous_closes(parsed_day)
        candidates = []

        for item in grouped_results:
            ticker = item.get("T")
            if active_tickers and ticker not in active_tickers:
                continue

            open_price = safe_float(item.get("o"))
            close_price = safe_float(item.get("c"))
            high_price = safe_float(item.get("h"))
            volume = safe_float(item.get("v"))
            price = close_price or high_price
            change_pct = abs(pct_diff(close_price, open_price) or 0)

            if price < MIN_STOCK_PRICE:
                continue

            if ticker:
                candidates.append(
                    {
                        "ticker": ticker,
                        "day": parsed_day,
                        "price": price,
                        "prev_close": previous_closes.get(ticker, open_price),
                        "daily_volume": volume,
                        "daily_change_pct": change_pct,
                    }
                )

        candidates.sort(
            key=lambda x: (
                safe_float(x.get("daily_change_pct")),
                safe_float(x.get("daily_volume")),
                safe_float(x.get("price")),
            ),
            reverse=True,
        )
        return self._rank_watchlist_candidates(candidates, parsed_day.isoformat())

    def get_auto_watchlist(
        self, day: Optional[Union[str, dt.date, dt.datetime]] = None
    ) -> List[str]:
        parsed_day = self._parse_watchlist_day(day)
        if not USE_AUTO_WATCHLIST:
            return self.base_tickers

        if parsed_day is not None:
            try:
                return self.get_historical_auto_watchlist(parsed_day)
            except Exception as e:
                print(f"Historical auto-watchlist error for {parsed_day}: {e}")
                return self.base_tickers

        url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"

        try:
            data = self._request_polygon_json(url)
            today = dt.datetime.now(MARKET_TZ).date()
            candidates = []

            for item in data.get("tickers", []):
                ticker = item.get("ticker")
                day = item.get("day", {})
                last_trade = item.get("lastTrade", {})
                prev_day = item.get("prevDay", {}) or {}

                change_pct = abs(safe_float(item.get("todaysChangePerc")))
                volume = safe_float(day.get("v"))
                price = safe_float(last_trade.get("p"))

                if price < MIN_STOCK_PRICE:
                    continue

                if ticker:
                    candidates.append(
                        {
                            "ticker": ticker,
                            "day": today,
                            "price": price,
                            "prev_close": safe_float(prev_day.get("c")),
                            "daily_volume": volume,
                            "daily_change_pct": change_pct,
                        }
                    )

            candidates.sort(
                key=lambda x: (
                    safe_float(x.get("daily_change_pct")),
                    safe_float(x.get("daily_volume")),
                    safe_float(x.get("price")),
                ),
                reverse=True,
            )
            return self._rank_watchlist_candidates(
                candidates, "snapshot+extended+options"
            )

        except Exception as e:
            print(f"Auto-watchlist error: {e}")
            return self.base_tickers

    def cooldown_active(self, ticker, direction):
        last = self.state[ticker]["last_alert_time"].get(direction)
        return last and time.time() - last < ALERT_COOLDOWN_SEC

    def _early_session_cutoff(self):
        try:
            hour, minute = str(EARLY_SESSION_END_TIME).split(":", 1)
            return dt.time(int(hour), int(minute))
        except Exception:
            return dt.time(10, 30)

    def is_early_session_time(self, when=None):
        if not EARLY_SESSION_GRACE_ENABLED:
            return False

        now = when or dt.datetime.now(MARKET_TZ)
        if isinstance(now, dt.datetime):
            now_time = now.astimezone(MARKET_TZ).time() if now.tzinfo else now.time()
        else:
            now_time = now

        return dt.time(9, 30) <= now_time <= self._early_session_cutoff()

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

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)

        return sum(trs[-period:]) / period if len(trs) >= period else None

    def aggregate_bars(self, bars, group_size):
        grouped = []

        for i in range(0, len(bars), group_size):
            chunk = bars[i : i + group_size]

            if len(chunk) < group_size:
                continue

            grouped.append(
                {
                    "open": safe_float(chunk[0].open),
                    "high": max(safe_float(x.high) for x in chunk),
                    "low": min(safe_float(x.low) for x in chunk),
                    "close": safe_float(chunk[-1].close),
                    "volume": sum(safe_float(x.volume) for x in chunk),
                }
            )

        return grouped

    def timeframe_trend(self, bars):
        """Return trend without forcing a full 21 higher-timeframe candles.

        A fixed EMA9/EMA21 requirement made the 15-minute trend stay NEUTRAL
        until 21 completed 15-minute candles were available, which is roughly
        2:45pm ET / 1:45pm CT.  During the morning session that prevented clean
        ETF weakness/strength from contributing to alert scoring.  Use shorter
        EMA pairs while the session is still young, then graduate to the normal
        9/21 pair once enough bars exist.
        """
        if len(bars) < 6:
            return "NEUTRAL"

        closes = [safe_float(x["close"]) for x in bars]

        if len(closes) >= 21:
            fast_length, slow_length = 9, 21
        elif len(closes) >= 12:
            fast_length, slow_length = 5, 9
        else:
            fast_length, slow_length = 3, 5

        ema_fast = self.ema(closes, fast_length)
        ema_slow = self.ema(closes, slow_length)

        if ema_fast is None or ema_slow is None:
            return "NEUTRAL"

        if closes[-1] > ema_fast > ema_slow:
            return "BULLISH"

        if closes[-1] < ema_fast < ema_slow:
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

        return (pm_high is not None and price > pm_high) or (
            pd_high is not None and price > pd_high
        )

    def put_below_pm_or_pd_low(self, tech):
        price = tech["price"]
        pm_low = tech.get("premarket_low")
        pd_low = tech.get("prev_low")

        return (pm_low is not None and price < pm_low) or (
            pd_low is not None and price < pd_low
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
            tech.get("vwap")
            and price > tech["vwap"]
            and tech.get("ema9")
            and tech.get("ema21")
            and tech["ema9"] > tech["ema21"]
        )

        bearish = (
            tech.get("vwap")
            and price < tech["vwap"]
            and tech.get("ema9")
            and tech.get("ema21")
            and tech["ema9"] < tech["ema21"]
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

    def build_daily_technical_context(self, ticker, daily, day):
        daily_closes = [safe_float(x.close) for x in daily if x.close is not None]
        daily_highs = [safe_float(x.high) for x in daily if x.high is not None]
        daily_lows = [safe_float(x.low) for x in daily if x.low is not None]
        daily_volumes = [safe_float(x.volume) for x in daily if x.volume is not None]

        if not daily_closes:
            return None

        dma20 = self.sma(daily_closes, DMA_SHORT)
        dma50 = self.sma(daily_closes, DMA_FAST)
        dma200 = self.sma(daily_closes, DMA_SLOW)
        atr14 = self.atr(daily, ATR_PERIOD)

        prev = daily[-2] if len(daily) >= 2 else None
        prev_high = safe_float(prev.high) if prev else None
        prev_low = safe_float(prev.low) if prev else None

        last_20_daily = daily[-20:] if len(daily) >= 20 else daily
        recent_high = (
            max([safe_float(x.high) for x in last_20_daily]) if last_20_daily else None
        )
        recent_low = (
            min([safe_float(x.low) for x in last_20_daily]) if last_20_daily else None
        )

        avg_20_volume = (
            sum(daily_volumes[-20:]) / 20 if len(daily_volumes) >= 20 else None
        )
        current_volume = daily_volumes[-1] if daily_volumes else None
        rel_volume = (
            current_volume / avg_20_volume
            if current_volume is not None and avg_20_volume
            else None
        )

        price = daily_closes[-1]

        daily_trend = "NEUTRAL"
        if dma20 and dma50:
            if price > dma20 > dma50:
                daily_trend = "BULLISH"
            elif price < dma20 < dma50:
                daily_trend = "BEARISH"

        weekly_trend = "NEUTRAL"
        if len(daily_closes) >= 6:
            week_change = pct_diff(daily_closes[-1], daily_closes[-6])
            if week_change is not None and week_change >= 1:
                weekly_trend = "BULLISH"
            elif week_change is not None and week_change <= -1:
                weekly_trend = "BEARISH"

        return {
            "ticker": ticker,
            "trading_day": str(day),
            "price": price,
            "vwap": None,
            "ema9": None,
            "ema21": None,
            "ema50": None,
            "dma20": dma20,
            "dma50": dma50,
            "dma200": dma200,
            "atr14": atr14,
            "trend_5m": "NEUTRAL",
            "trend_15m": "NEUTRAL",
            "daily_trend": daily_trend,
            "weekly_trend": weekly_trend,
            "orb_high": None,
            "orb_low": None,
            "premarket_high": None,
            "premarket_low": None,
            "prev_high": prev_high,
            "prev_low": prev_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "previous_recent_high": prev_high,
            "previous_recent_low": prev_low,
            "current_volume": current_volume,
            "avg_20_volume": avg_20_volume,
            "rel_volume": rel_volume,
            "daily_current_volume": current_volume,
            "daily_avg_20_volume": avg_20_volume,
            "daily_closes": daily_closes,
            "last_60_closes": daily_closes[-60:],
            "last_5_closes": daily_closes[-5:],
            "last_5_lows": daily_lows[-5:],
            "last_5_highs": daily_highs[-5:],
            "intraday_available": False,
        }

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

        daily_tech = self.build_daily_technical_context(ticker, daily, day)
        if not daily_tech:
            print(f"{ticker}: daily context unavailable")
            return None

        if not minute:
            print(f"{ticker}: no minute data for {day}; using daily swing context")
            self.tech_cache[ticker] = daily_tech
            self.tech_cache_time[ticker] = now_ts
            return daily_tech

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
                f"Current ET={dt.datetime.now(MARKET_TZ).strftime('%H:%M:%S')}; "
                "using daily swing context"
            )
            self.tech_cache[ticker] = daily_tech
            self.tech_cache_time[ticker] = now_ts
            return daily_tech

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
                safe_float(bar.high) + safe_float(bar.low) + safe_float(bar.close)
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
        previous_recent_high = (
            max([safe_float(x.high) for x in prev_10]) if prev_10 else None
        )
        previous_recent_low = (
            min([safe_float(x.low) for x in prev_10]) if prev_10 else None
        )

        bars_5m = self.aggregate_bars(regular, 5)
        bars_15m = self.aggregate_bars(regular, 15)

        trend_5m = self.timeframe_trend(bars_5m)
        trend_15m = self.timeframe_trend(bars_15m)

        price = safe_float(regular[-1].close)

        tech = dict(daily_tech)
        latest_regular_ts = dt.datetime.fromtimestamp(
            regular[-1].timestamp / 1000,
            tz=dt.timezone.utc,
        ).astimezone(MARKET_TZ)

        tech.update(
            {
                "price": price,
                "vwap": vwap,
                "ema9": ema9,
                "ema21": ema21,
                "ema50": ema50,
                "trend_5m": trend_5m,
                "trend_15m": trend_15m,
                "orb_high": orb_high,
                "orb_low": orb_low,
                "premarket_high": pm_high,
                "premarket_low": pm_low,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "previous_recent_high": previous_recent_high,
                "previous_recent_low": previous_recent_low,
                "current_volume": current_volume,
                "avg_20_volume": avg_20_volume,
                "intraday_current_volume": current_volume,
                "intraday_avg_20_volume": avg_20_volume,
                "regular_bars_count": len(regular),
                "latest_regular_time": latest_regular_ts.strftime("%H:%M"),
                "early_session_setup": self.is_early_session_time(latest_regular_ts),
                "last_5_closes": [safe_float(x.close) for x in regular[-5:]],
                "last_5_lows": [safe_float(x.low) for x in regular[-5:]],
                "last_5_highs": [safe_float(x.high) for x in regular[-5:]],
                "last_5_intraday_closes": [safe_float(x.close) for x in regular[-5:]],
                "last_5_intraday_lows": [safe_float(x.low) for x in regular[-5:]],
                "last_5_intraday_highs": [safe_float(x.high) for x in regular[-5:]],
                "intraday_available": True,
            }
        )

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

            touched = any(
                self.is_near_level(low, level, RETEST_TOLERANCE_PCT) for low in lows
            )
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

            touched = any(
                self.is_near_level(high, level, RETEST_TOLERANCE_PCT) for high in highs
            )
            rejected = price < level

            if touched and rejected:
                return True, f"retest confirmed at {name}"

        return False, "no clean bearish retest"

    def detect_late_breakout(self, direction, tech):
        price = tech["price"]
        regime = self.get_market_regime()
        extension_multiplier = 1.0
        if ENABLE_REGIME_SCORING:
            if regime == "CHOP":
                extension_multiplier = CHOP_EXTENSION_MULTIPLIER
            elif regime == "TREND":
                extension_multiplier = TREND_EXTENSION_MULTIPLIER

        vwap_limit = MAX_EXTENSION_FROM_VWAP_PCT * extension_multiplier
        orb_limit = MAX_EXTENSION_FROM_ORB_PCT * extension_multiplier
        vwap_ext = abs(pct_diff(price, tech.get("vwap"))) if tech.get("vwap") else 0

        if vwap_ext > vwap_limit:
            return (
                True,
                f"price extended {vwap_ext:.2f}% from VWAP (limit {vwap_limit:.2f}%, {regime})",
            )

        if direction == "CALL":
            levels = [
                tech.get("orb_high"),
                tech.get("premarket_high"),
                tech.get("prev_high"),
            ]
            label = "breakout"
        else:
            levels = [
                tech.get("orb_low"),
                tech.get("premarket_low"),
                tech.get("prev_low"),
            ]
            label = "breakdown"

        extension = max([abs(pct_diff(price, x)) for x in levels if x] or [0])

        if extension > orb_limit:
            return (
                True,
                f"price extended {extension:.2f}% beyond {label} level (limit {orb_limit:.2f}%, {regime})",
            )

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

    def microstructure_ok(self, direction, tech):
        closes = tech.get("last_5_closes", [])
        highs = tech.get("last_5_highs", [])
        lows = tech.get("last_5_lows", [])
        if len(closes) < 3 or len(highs) < 3 or len(lows) < 3:
            return False, "insufficient recent candles"

        c1, c2, c3 = closes[-3], closes[-2], closes[-1]
        h3, l3 = highs[-1], lows[-1]
        rng3 = max(h3 - l3, 1e-9)
        body3 = abs(c3 - c2)
        body_ratio = body3 / rng3

        if direction == "CALL":
            if not (c3 > c2 >= c1):
                return False, "last 3 closes not stacking bullish"
        else:
            if not (c3 < c2 <= c1):
                return False, "last 3 closes not stacking bearish"

        if body_ratio < 0.35:
            return False, "last candle body too small vs range"

        return True, "microstructure confirms follow-through"

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

    def get_market_regime(self):
        market = self.get_market_bias()
        spread = abs(market["bullish_count"] - market["bearish_count"])
        if spread >= 2:
            return "TREND"
        if market["bias"] == "NEUTRAL":
            return "CHOP"
        return "MIXED"

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

        micro_ok, micro_reason = self.microstructure_ok("CALL", tech)
        if micro_ok:
            score += 6
            reasons.append(micro_reason)
        else:
            score -= 8
            reasons.append("microstructure weak: " + micro_reason)

        market = self.get_market_bias()

        if market["bias"] == "BULLISH":
            score += MARKET_BIAS_WEIGHT
            reasons.append("market bias bullish: " + ", ".join(market["details"]))

        elif market["bias"] == "BEARISH":
            score -= MARKET_BIAS_WEIGHT
            reasons.append("market bias against CALLs: " + ", ".join(market["details"]))
            score -= MARKET_BIAS_CONFLICT_PENALTY
            reasons.append("extra penalty: CALL against market bias")

        elif REQUIRE_MARKET_BIAS:
            score -= MARKET_BIAS_WEIGHT
            reasons.append("market bias neutral, CALL deprioritized")

        if self.call_above_pm_or_pd_high(tech):
            score += A_PLUS_BREAKOUT_BONUS
            reasons.append(
                "A+ CALL condition met: price above premarket high or previous day high"
            )
        elif REQUIRE_PM_OR_PD_BREAK_FOR_A_PLUS:
            score -= A_PLUS_BREAKOUT_PENALTY
            reasons.append(
                "A+ CALL blocked: price not above premarket high or previous day high"
            )

        sector_status, sector_reason = self.get_sector_confirmation(
            tech["ticker"], "CALL"
        )

        if sector_status == "CONFIRMED":
            score += SECTOR_ETF_WEIGHT
            reasons.append(sector_reason)
        elif sector_status == "CONFLICT":
            score -= SECTOR_ETF_WEIGHT
            reasons.append(sector_reason)
        elif REQUIRE_SECTOR_CONFIRMATION:
            score -= SECTOR_ETF_WEIGHT
            reasons.append("sector ETF confirmation missing")

        if ENABLE_REGIME_SCORING and self.get_market_regime() == "CHOP":
            score -= CHOP_MIN_SCORE_BONUS
            reasons.append("chop regime: stricter CALL scoring")

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

        micro_ok, micro_reason = self.microstructure_ok("PUT", tech)
        if micro_ok:
            score += 6
            reasons.append(micro_reason)
        else:
            score -= 8
            reasons.append("microstructure weak: " + micro_reason)

        market = self.get_market_bias()

        if market["bias"] == "BEARISH":
            score += MARKET_BIAS_WEIGHT
            reasons.append("market bias bearish: " + ", ".join(market["details"]))

        elif market["bias"] == "BULLISH":
            score -= MARKET_BIAS_WEIGHT
            reasons.append("market bias against PUTs: " + ", ".join(market["details"]))
            score -= MARKET_BIAS_CONFLICT_PENALTY
            reasons.append("extra penalty: PUT against market bias")

        elif REQUIRE_MARKET_BIAS:
            score -= MARKET_BIAS_WEIGHT
            reasons.append("market bias neutral, PUT deprioritized")

        if self.put_below_pm_or_pd_low(tech):
            score += A_PLUS_BREAKOUT_BONUS
            reasons.append(
                "A+ PUT condition met: price below premarket low or previous day low"
            )
        elif REQUIRE_PM_OR_PD_BREAK_FOR_A_PLUS:
            score -= A_PLUS_BREAKOUT_PENALTY
            reasons.append(
                "A+ PUT blocked: price not below premarket low or previous day low"
            )

        sector_status, sector_reason = self.get_sector_confirmation(
            tech["ticker"], "PUT"
        )

        if sector_status == "CONFIRMED":
            score += SECTOR_ETF_WEIGHT
            reasons.append(sector_reason)
        elif sector_status == "CONFLICT":
            score -= SECTOR_ETF_WEIGHT
            reasons.append(sector_reason)
        elif REQUIRE_SECTOR_CONFIRMATION:
            score -= SECTOR_ETF_WEIGHT
            reasons.append("sector ETF confirmation missing")

        if ENABLE_REGIME_SCORING and self.get_market_regime() == "CHOP":
            score -= CHOP_MIN_SCORE_BONUS
            reasons.append("chop regime: stricter PUT scoring")

        return {
            "direction": "PUT",
            "score": max(score, 0),
            "reasons": reasons,
            "retest_confirmed": retest_ok,
            "late_breakout_risk": late,
            "late_reason": late_reason,
        }
