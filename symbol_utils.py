import re

# TradingView exchange map for common US stocks/ETFs in this project.
# Default is NASDAQ because most tech/momentum names in the watchlist are NASDAQ-listed.
TV_EXCHANGE_OVERRIDES = {
    # ETFs
    "SPY": "AMEX", "QQQ": "NASDAQ", "IWM": "AMEX", "DIA": "AMEX", "SMH": "NASDAQ",
    "SOXX": "NASDAQ", "ARKK": "AMEX", "TQQQ": "NASDAQ", "SQQQ": "NASDAQ",
    "USO": "AMEX", "XLF": "AMEX", "XLE": "AMEX", "XLK": "AMEX", "XLY": "AMEX",

    # NYSE-listed common names
    "ORCL": "NYSE", "PLTR": "NASDAQ", "UBER": "NYSE", "RIVN": "NASDAQ", "NIO": "NYSE",
    "BA": "NYSE", "JPM": "NYSE", "BAC": "NYSE", "GS": "NYSE", "MS": "NYSE", "WFC": "NYSE",
    "XOM": "NYSE", "CVX": "NYSE", "OXY": "NYSE", "SLB": "NYSE", "FCX": "NYSE", "CLF": "NYSE",
    "LLY": "NYSE", "NVO": "NYSE", "UNH": "NYSE", "NKE": "NYSE", "SBUX": "NASDAQ",
    "MCD": "NYSE", "COST": "NASDAQ", "WMT": "NYSE", "HD": "NYSE", "LOW": "NYSE",
    "UAL": "NASDAQ", "DAL": "NYSE", "AAL": "NASDAQ", "CCL": "NYSE", "RCL": "NYSE",
    "ABNB": "NASDAQ", "V": "NYSE", "MA": "NYSE", "AXP": "NYSE", "F": "NYSE", "GM": "NYSE",
    "SNOW": "NYSE", "CRM": "NYSE", "NOW": "NYSE", "SHOP": "NYSE", "AI": "NYSE",
}

# Common aliases users or feeds may emit.
SYMBOL_ALIASES = {
    "BRK.B": "BRK-B",
    "BRK/B": "BRK-B",
    "BF.B": "BF-B",
    "BF/B": "BF-B",
}

VALID_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def normalize_symbol(raw_symbol: str) -> str:
    """Normalize incoming ticker strings for Polygon/Yahoo/internal use.

    Examples:
    - "NASDAQ:ORCL" -> "ORCL"
    - " nasdaq:orcl " -> "ORCL"
    - "BRK.B" -> "BRK-B"
    """
    if raw_symbol is None:
        return ""

    symbol = str(raw_symbol).strip().upper()

    # Remove TradingView/broker exchange prefixes.
    if ":" in symbol:
        symbol = symbol.split(":")[-1]

    # Remove accidental asset suffixes often found in copied watchlists.
    for suffix in [" US", ".US", "-USD"]:
        if symbol.endswith(suffix):
            symbol = symbol[: -len(suffix)]

    symbol = symbol.replace("/", ".")
    symbol = SYMBOL_ALIASES.get(symbol, symbol)
    symbol = symbol.strip()
    return symbol


def is_valid_symbol(raw_symbol: str) -> bool:
    symbol = normalize_symbol(raw_symbol)
    if not symbol:
        return False
    if not VALID_SYMBOL_RE.match(symbol):
        return False
    # Avoid obvious non-equity/index placeholders from TradingView sidebars.
    if symbol in {"", "INVALID", "SYMBOL", "WATCHLIST"}:
        return False
    return True


def tradingview_symbol(raw_symbol: str) -> str:
    """Return a TradingView-compatible symbol with exchange prefix."""
    symbol = normalize_symbol(raw_symbol)
    exchange = TV_EXCHANGE_OVERRIDES.get(symbol, "NASDAQ")
    return f"{exchange}:{symbol}"
