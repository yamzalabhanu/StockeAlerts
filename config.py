import os

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
    
OPENAI_API_KEY = "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"
POLYGON_API_KEY = "pphY2Krt4dAsQMnHjV_VR3AhvSZLdBPj"
TELEGRAM_TOKEN = "7569824254:AAGl7qmYJqWMRIkkqCwmDt6XnO59FEalJOw"
TELEGRAM_CHAT_ID = "7866545451"

MARKET_TZ = ZoneInfo("America/New_York")

BASE_WATCHLIST = [
    # Mega-cap / high-liquidity tech
    "NVDA", "AMD", "AVGO", "TSM", "ARM", "MU", "INTC", "SMCI",
    "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "NFLX",

    # AI / cloud / software momentum
    "PLTR", "SNOW", "CRM", "ORCL", "ADBE", "NOW", "DDOG", "NET",
    "CRWD", "PANW", "MDB", "AI",

    # Semiconductor / memory / optical / hardware
    "SNDK", "LITE", "AAOI", "MRVL", "QCOM", "AMAT", "LRCX", "KLAC",
    "ON", "MPWR", "ALAB", "DELL", "HPE",

    # Quantum / high-beta tech
    "IONQ", "RGTI", "QBTS", "QUBT", "ARQQ",

    # Crypto / fintech momentum
    "COIN", "MSTR", "MARA", "RIOT", "HOOD", "SOFI", "AFRM", "PYPL",
    "SQ", "UPST",

    # EV / energy / industrial momentum
    "TSLA", "RIVN", "LCID", "NIO", "XPEV", "LI", "F", "GM",
    "XOM", "CVX", "OXY", "SLB", "USO", "FCX", "CLF", "NEM",

    # Defense / aerospace / space
    "LMT", "RTX", "NOC", "BA", "RKLB", "ACHR", "JOBY",

    # Consumer / travel / active names
    "COST", "WMT", "HD", "LOW", "NKE", "SBUX", "MCD",
    "UAL", "DAL", "AAL", "CCL", "RCL", "ABNB", "UBER",

    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "AXP",

    # Healthcare / biotech high beta
    "LLY", "NVO", "UNH", "VRTX", "MRNA", "BIIB", "REGN", "AXSM",

    # ETFs / market direction
    "SPY", "QQQ", "IWM", "DIA", "SMH", "SOXX", "ARKK", "TQQQ", "SQQQ"
]

USE_AUTO_WATCHLIST = True
AUTO_WATCHLIST_LIMIT = 40
MIN_AUTO_VOLUME = 2_000_000
MIN_AUTO_CHANGE_PCT = 2.0
MIN_STOCK_PRICE = 8

MARKET_BIAS_TICKERS = ["SPY", "QQQ", "IWM", "SMH"]
MARKET_BIAS_WEIGHT = 15
REQUIRE_MARKET_BIAS = False

REQUIRE_PM_OR_PD_BREAK_FOR_A_PLUS = True
A_PLUS_BREAKOUT_BONUS = 20
A_PLUS_BREAKOUT_PENALTY = 35

SCAN_INTERVAL_SEC = 300
ALERT_COOLDOWN_SEC = 900

EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50

DMA_SHORT = 20
DMA_FAST = 50
DMA_SLOW = 200

ORB_MINUTES = 15

MIN_CALL_SCORE = 90
MIN_PUT_SCORE = 90
MIN_AI_CONFIDENCE = 85

MAX_EXTENSION_FROM_VWAP_PCT = 2.5
MAX_EXTENSION_FROM_ORB_PCT = 1.5
RETEST_TOLERANCE_PCT = 0.35
MIN_RISK_REWARD = 1.8
REQUIRE_RETEST = True

RELATIVE_STRENGTH_WEIGHT = 10
VOLUME_SPIKE_WEIGHT = 10
CONTINUATION_WEIGHT = 10
VOLUME_SPIKE_MULTIPLIER = 1.5

ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 1.2
ATR_TARGET_MULTIPLIER = 2.2

CONFIRM_5M_15M = False
TIMEFRAME_CONFIRM_WEIGHT = 5

SUPPORT_RESISTANCE_BUFFER_PCT = 0.35
FAILED_BREAKOUT_WEIGHT = 30
SR_REJECTION_WEIGHT = 25

RANK_TOP_ALERTS_ONLY = True
MAX_ALERTS_PER_SCAN = 5

# Hard A+ breakout gate
REQUIRE_PM_OR_PD_BREAK_FOR_A_PLUS = True
A_PLUS_BREAKOUT_BONUS = 20
A_PLUS_BREAKOUT_PENALTY = 35

# Quality trading windows ET
QUALITY_WINDOWS = [
    ("09:30", "12:30"),
    ("13:30", "15:30"),
]

# Sector ETF confirmation
SECTOR_ETF_WEIGHT = 15
REQUIRE_SECTOR_CONFIRMATION = True

SECTOR_ETF_MAP = {
    "NVDA": "SMH", "AMD": "SMH", "AVGO": "SMH", "MU": "SMH", "SMCI": "SMH",
    "JPM": "XLF", "BAC": "XLF", "GS": "XLF",
    "XOM": "XLE", "CVX": "XLE", "OXY": "XLE",
    "TSLA": "XLY", "AMZN": "XLY",
}

LOG_FILE = "stock_technical_alerts.csv"
