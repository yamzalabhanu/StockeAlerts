import os

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


MARKET_TZ = ZoneInfo("America/New_York")

# --- ALERT MODES ---
ENABLE_INTRADAY_ALERTS = True
ENABLE_SWING_ALERTS = True

INTRADAY_MIN_SCORE = 75
SWING_MIN_SCORE = 80

SWING_HOLD_DAYS_MIN = 2
SWING_HOLD_DAYS_MAX = 10
SWING_PULLBACK_TOLERANCE_PCT = 1.0
SWING_ATR_STOP_MULTIPLIER = 1.5
SWING_ATR_TARGET_MULTIPLIER = 4.0

# --- RISK MANAGEMENT ---
ACCOUNT_SIZE = 100000
RISK_PER_TRADE_PCT = 0.01
MAX_POSITION_PCT = 0.2

BASE_WATCHLIST = [
    "NVDA", "AMD", "AVGO", "TSM", "ARM", "MU", "INTC", "SMCI",
    "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "NFLX",
    "PLTR", "SNOW", "CRM", "ORCL", "ADBE", "NOW", "DDOG", "NET",
    "CRWD", "PANW", "MDB", "AI",
    "SNDK", "LITE", "AAOI", "MRVL", "QCOM", "AMAT", "LRCX", "KLAC",
    "ON", "MPWR", "ALAB", "DELL", "HPE",
    "IONQ", "RGTI", "QBTS", "QUBT", "ARQQ",
    "COIN", "MSTR", "MARA", "RIOT", "HOOD", "SOFI", "AFRM", "PYPL",
    "SQ", "UPST",
    "RIVN", "LCID", "NIO", "XPEV", "LI", "F", "GM",
    "XOM", "CVX", "OXY", "SLB", "USO", "FCX", "CLF", "NEM",
    "LMT", "RTX", "NOC", "BA", "RKLB", "ACHR", "JOBY",
    "COST", "WMT", "HD", "LOW", "NKE", "SBUX", "MCD",
    "UAL", "DAL", "AAL", "CCL", "RCL", "ABNB", "UBER",
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "AXP",
    "LLY", "NVO", "UNH", "VRTX", "MRNA", "BIIB", "REGN", "AXSM",
    "SPY", "QQQ", "IWM", "DIA", "SMH", "SOXX", "ARKK", "TQQQ", "SQQQ"
]

USE_AUTO_WATCHLIST = True
AUTO_WATCHLIST_LIMIT = 40
MIN_AUTO_VOLUME = 2_000_000
MIN_AUTO_CHANGE_PCT = 2.0
MIN_STOCK_PRICE = 8

# (rest unchanged below)
