import csv
import datetime as dt
from pathlib import Path
from typing import Iterable, Optional, Set

from config import LOG_FILE, MARKET_TZ

_ALERTED_TICKERS_BY_DAY = {}
_LOADED_LOG_DAYS = set()


def alert_day(now: Optional[dt.datetime] = None) -> dt.date:
    """Return the market-local day used for same-day alert de-duplication."""
    if now is None:
        return dt.datetime.now(MARKET_TZ).date()

    if now.tzinfo is None:
        now = now.replace(tzinfo=MARKET_TZ)
    else:
        now = now.astimezone(MARKET_TZ)
    return now.date()


def normalize_ticker(ticker: str) -> str:
    return str(ticker or "").strip().upper()


def _parse_timestamp_day(timestamp: str) -> Optional[dt.date]:
    if not timestamp:
        return None

    raw = str(timestamp).strip()
    if not raw:
        return None

    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(MARKET_TZ).date()


def _read_logged_tickers_for_day(day: dt.date) -> Set[str]:
    path = Path(LOG_FILE)
    if not path.exists():
        return set()

    tickers = set()
    try:
        with path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if _parse_timestamp_day(row.get("timestamp")) != day:
                    continue
                ticker = normalize_ticker(row.get("ticker"))
                if ticker:
                    tickers.add(ticker)
    except Exception as e:
        print(f"Alert history load skipped: {e}")

    return tickers


def _ensure_day_loaded(day: dt.date) -> Set[str]:
    if day not in _ALERTED_TICKERS_BY_DAY:
        _ALERTED_TICKERS_BY_DAY[day] = set()

    if day not in _LOADED_LOG_DAYS:
        _ALERTED_TICKERS_BY_DAY[day].update(_read_logged_tickers_for_day(day))
        _LOADED_LOG_DAYS.add(day)

    stale_days = [cached_day for cached_day in _ALERTED_TICKERS_BY_DAY if cached_day != day]
    for stale_day in stale_days:
        _ALERTED_TICKERS_BY_DAY.pop(stale_day, None)
        _LOADED_LOG_DAYS.discard(stale_day)

    return _ALERTED_TICKERS_BY_DAY[day]


def alerted_tickers_today(day: Optional[dt.date] = None) -> Set[str]:
    """Return tickers that already produced any alert on the selected market day."""
    day = day or alert_day()
    return set(_ensure_day_loaded(day))


def was_alerted_today(ticker: str, day: Optional[dt.date] = None) -> bool:
    ticker = normalize_ticker(ticker)
    if not ticker:
        return False
    day = day or alert_day()
    return ticker in _ensure_day_loaded(day)


def mark_alerted_today(ticker: str, day: Optional[dt.date] = None) -> None:
    ticker = normalize_ticker(ticker)
    if not ticker:
        return
    day = day or alert_day()
    _ensure_day_loaded(day).add(ticker)


def mark_alerted_tickers_today(tickers: Iterable[str], day: Optional[dt.date] = None) -> None:
    day = day or alert_day()
    for ticker in tickers:
        mark_alerted_today(ticker, day=day)
