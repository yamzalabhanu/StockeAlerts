import os

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("America/New_York")

# --- RISK MANAGEMENT ---
ACCOUNT_SIZE = 100000
RISK_PER_TRADE_PCT = 0.01
MAX_POSITION_PCT = 0.2

# (rest unchanged)
