from __future__ import annotations

from typing import Any, Dict

from bot_utils import safe_float
from market_data import get_stock_data, compute_indicators

SECTOR_MAP = {
    "NVDA": "SMH",
    "AMD": "SMH",
    "AVGO": "SMH",
    "TSM": "SMH",
    "MU": "SMH",
    "AAPL": "QQQ",
    "MSFT": "QQQ",
    "TSLA": "QQQ",
    "AMZN": "QQQ",
    "META": "QQQ",
    "GOOGL": "QQQ",
    "JPM": "XLF",
    "GS": "XLF",
    "BAC": "XLF",
    "XOM": "XLE",
    "CVX": "XLE",
}


def sector_confirm(symbol: str) -> tuple[bool, str]:
    sector = SECTOR_MAP.get(symbol)
    if not sector:
        return True, "No sector mapping"

    df = compute_indicators(get_stock_data(sector))
    latest = df.iloc[-1]

    bullish = latest.Close > latest.EMA21
    bearish = latest.Close < latest.EMA21

    if bullish:
        return True, f"Sector {sector} strong"
    elif bearish:
        return False, f"Sector {sector} weak"

    return False, "Sector neutral"


def _pct_change(df, lookback: int = 5) -> float:
    if df is None or len(df) <= lookback:
        return 0.0
    close = df["Close"] if "Close" in df else df["close"]
    current = safe_float(close.iloc[-1], 0) or 0
    previous = safe_float(close.iloc[-lookback], 0) or 0
    return ((current - previous) / previous) * 100 if previous else 0.0


def sector_relative_strength(symbol: str, symbol_df=None, sector_df=None, lookback: int = 5) -> Dict[str, Any]:
    """Measure leader/laggard status versus the symbol's sector ETF.

    Positive relative strength means the symbol is outperforming its ETF; a CALL
    in that state receives a higher-quality context, while a PUT wants relative
    weakness.  This lets semiconductor names (NVDA/AMD/etc.) respect SMH/SOXX
    instead of trading in isolation.
    """
    symbol = str(symbol or "").upper()
    sector = SECTOR_MAP.get(symbol)
    if not sector:
        return {"status": "UNMAPPED", "sector": None, "score": 50, "relative_performance_pct": 0.0, "label": "unmapped"}

    try:
        symbol_df = symbol_df if symbol_df is not None else compute_indicators(get_stock_data(symbol))
        sector_df = sector_df if sector_df is not None else compute_indicators(get_stock_data(sector))
        symbol_change = _pct_change(symbol_df, lookback)
        sector_change = _pct_change(sector_df, lookback)
    except Exception as e:
        return {"status": "UNAVAILABLE", "sector": sector, "score": 50, "relative_performance_pct": 0.0, "label": f"unavailable: {e}"}

    relative = symbol_change - sector_change
    if relative >= 1.5:
        label = "leader"
        score = 80
    elif relative >= 0.4:
        label = "outperforming"
        score = 65
    elif relative <= -1.5:
        label = "laggard"
        score = 20
    elif relative <= -0.4:
        label = "underperforming"
        score = 35
    else:
        label = "in_line"
        score = 50

    return {
        "status": "OK",
        "sector": sector,
        "score": score,
        "symbol_change_pct": round(symbol_change, 2),
        "sector_change_pct": round(sector_change, 2),
        "relative_performance_pct": round(relative, 2),
        "label": label,
    }


def sector_direction_adjustment(symbol: str, direction: str, relative_strength: Dict[str, Any] | None = None) -> Dict[str, Any]:
    rs = relative_strength or sector_relative_strength(symbol)
    score = 0
    direction = str(direction or "").upper()
    label = rs.get("label")
    if direction == "CALL":
        if label in {"leader", "outperforming"}:
            score = 8
        elif label in {"laggard", "underperforming"}:
            score = -12
    elif direction == "PUT":
        if label in {"laggard", "underperforming"}:
            score = 8
        elif label in {"leader", "outperforming"}:
            score = -12
    return {"adjustment": score, "relative_strength": rs, "reason": f"{symbol} is {label} vs {rs.get('sector')}"}
