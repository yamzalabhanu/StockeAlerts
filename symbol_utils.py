import re
from typing import List

TV_EXCHANGE_OVERRIDES = {
    "SPY": "AMEX", "QQQ": "NASDAQ", "IWM": "AMEX", "DIA": "AMEX", "SMH": "NASDAQ",
    "SOXX": "NASDAQ", "ARKK": "AMEX", "TQQQ": "NASDAQ", "SQQQ": "NASDAQ",
    "USO": "AMEX", "XLF": "AMEX", "XLE": "AMEX", "XLK": "AMEX", "XLY": "AMEX",
    "ORCL": "NYSE", "UBER": "NYSE", "NIO": "NYSE", "QBTS": "NYSE", "BA": "NYSE", "JPM": "NYSE",
    "BAC": "NYSE", "GS": "NYSE", "MS": "NYSE", "WFC": "NYSE", "XOM": "NYSE",
    "CVX": "NYSE", "OXY": "NYSE", "SLB": "NYSE", "FCX": "NYSE", "CLF": "NYSE",
    "LLY": "NYSE", "NVO": "NYSE", "UNH": "NYSE", "NKE": "NYSE", "MCD": "NYSE",
    "WMT": "NYSE", "HD": "NYSE", "LOW": "NYSE", "DAL": "NYSE", "CCL": "NYSE",
    "RCL": "NYSE", "V": "NYSE", "MA": "NYSE", "AXP": "NYSE", "F": "NYSE",
    "GM": "NYSE", "SNOW": "NYSE", "CRM": "NYSE", "NOW": "NYSE", "SHOP": "NYSE", "AI": "NYSE",
}

SYMBOL_ALIASES = {
    "BRK.B": "BRK-B", "BRK/B": "BRK-B", "BF.B": "BF-B", "BF/B": "BF-B",
    "NDQ": "QQQ", "NASDAQ": "QQQ",
}

# Index/sidebar symbols should not be treated as tradable equity tickers by the bot.
INVALID_SYMBOLS = {"", "INVALID", "SYMBOL", "WATCHLIST", "DXY", "VIX", "DJI", "SPX"}
VALID_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def normalize_symbol(raw_symbol: str) -> str:
    if raw_symbol is None:
        return ""

    symbol = str(raw_symbol).strip().upper()

    # Remove TradingView / broker prefixes: NASDAQ:ORCL -> ORCL
    if ":" in symbol:
        symbol = symbol.split(":")[-1]

    for suffix in [" US", ".US", "-USD", " USD"]:
        if symbol.endswith(suffix):
            symbol = symbol[: -len(suffix)]

    symbol = symbol.replace("/", ".")
    symbol = re.sub(r"[^A-Z0-9.\-]", "", symbol)
    symbol = SYMBOL_ALIASES.get(symbol, symbol)
    return symbol.strip()


def is_valid_symbol(raw_symbol: str) -> bool:
    symbol = normalize_symbol(raw_symbol)
    if not symbol or symbol in INVALID_SYMBOLS:
        return False
    return bool(VALID_SYMBOL_RE.match(symbol))


def tradingview_candidates(raw_symbol: str) -> List[str]:
    symbol = normalize_symbol(raw_symbol)
    if not is_valid_symbol(symbol):
        return []

    preferred = TV_EXCHANGE_OVERRIDES.get(symbol, "NASDAQ")
    exchanges = [preferred, "NASDAQ", "NYSE", "AMEX"]

    seen = set()
    out = []
    for exchange in exchanges:
        tv_symbol = f"{exchange}:{symbol}"
        if tv_symbol not in seen:
            out.append(tv_symbol)
            seen.add(tv_symbol)
    return out


def tradingview_symbol(raw_symbol: str) -> str:
    candidates = tradingview_candidates(raw_symbol)
    if not candidates:
        raise ValueError(f"Invalid TradingView symbol: {raw_symbol}")
    return candidates[0]


def normalize_watchlist(symbols):
    out = []
    seen = set()
    for item in symbols:
        symbol = normalize_symbol(item)
        if is_valid_symbol(symbol) and symbol not in seen:
            out.append(symbol)
            seen.add(symbol)
    return out
