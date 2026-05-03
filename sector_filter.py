SECTOR_MAP = {
    "NVDA": "SMH",
    "AMD": "SMH",
    "AAPL": "QQQ",
    "MSFT": "QQQ",
    "TSLA": "QQQ",
    "AMZN": "QQQ",
}

from market_data import get_stock_data, compute_indicators


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
