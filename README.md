# 🚀 StockeAlerts — Advanced Intraday Stock & Options Alert Bot

StockeAlerts is an advanced intraday stock and options alert system that combines:

- Rule-based technical scoring
- 5-minute intraday confirmation
- Smart entry-mode detection
- OpenAI trade-quality filtering
- TradingView chart screenshot validation
- Telegram alerts
- CSV logging and outcome tracking

The project is designed to scan high-liquidity stocks and ETFs, rank the best setups, and send structured trade alerts with entry, stop, target, risk/reward, and setup rationale.

---

## 🔥 Core Features

### 1. Advanced Technical Engine

The bot calculates and uses:

- VWAP
- EMA 9 / EMA 21 / EMA 50
- DMA 20 / DMA 50 / DMA 200
- ATR(14)
- ORB high/low
- Premarket high/low
- Previous-day high/low
- Recent high/low
- 5-minute and 15-minute trend state
- Volume spike detection
- Relative strength vs SPY
- Sector ETF confirmation
- Market bias using SPY, QQQ, IWM, and SMH

---

### 2. Auto Watchlist

The bot supports:

- Static watchlist from `BASE_WATCHLIST`
- Auto-expanded watchlist using Polygon snapshot movers
- Filters by:
  - Minimum stock price
  - Minimum volume
  - Minimum daily % move

---

### 3. Intraday Confirmation Engine

The bot uses recent 5-minute candles to validate trade timing.

Checks include:

- EMA alignment
- VWAP alignment
- Candle body confirmation
- Relative volume spike
- Trigger extension check

Adaptive confirmation logic:

```text
Score >= 75  → require 2 of 4 confirmations
Score < 75   → require 3 of 4 confirmations
```

Continuation entries are allowed up to roughly 2% extension from trigger.

---

## 🎯 Entry Modes

The bot now classifies each valid setup into an entry mode.

### BREAKOUT

Used when price breaks a meaningful level with volume and intraday confirmation.

Best for:

- ORB breakouts
- Premarket high breaks
- Previous-day high breaks
- Momentum expansion candles

### RETEST

Used when price breaks a level, pulls back, and reclaims/rejects it.

Best for:

- Cleaner entries
- Higher quality A/A+ setups
- Defined invalidation

### MOMENTUM

Used when price is already moving but still within acceptable extension.

Best for:

- Trend days
- Strong volume continuation
- Fast runners

### PULLBACK

Used when price pulls back toward EMA21 or VWAP and reclaims/holds.

Best for:

- Starter entries
- Controlled risk entries
- Dip-buy or rejection trades

---

## 🤖 AI Decision Engine

OpenAI is used to evaluate trade quality and timing.

The AI receives:

- Direction candidate
- Entry mode
- Rule score
- Technical context
- Intraday confirmation details
- Market bias
- ATR-based trade plan
- Setup reasons

The AI returns structured JSON:

```json
{
  "verdict": "BUY or WAIT",
  "confidence": 0,
  "entry": 0,
  "stop": 0,
  "target": 0,
  "risk_reward": 0,
  "setup_quality": "A+ / A / B / LOW",
  "entry_timing": "EARLY / IDEAL / LATE / CHOP",
  "retest_confirmed": true,
  "late_breakout_risk": false,
  "reason": "explanation"
}
```

### AI WAIT Override

The bot has a controlled override to prevent AI from over-rejecting strong setups.

Override can allow a trade when:

- Rule score is strong
- Intraday confirmations are strong
- Entry mode is BREAKOUT, RETEST, or MOMENTUM
- Risk/reward is acceptable
- Timing is not LATE or CHOP

---

## 📸 TradingView Chart Capture

For high-score setups, the bot can:

- Open TradingView using Playwright
- Capture a chart screenshot
- Send chart image + technical data to OpenAI
- Use visual validation to confirm or reject the setup

Files involved:

- `chart_capture.py`
- `bot.py`

---

## 📊 Ranking System

Each candidate receives a ranking score based on:

- Rule score
- AI confidence
- Risk/reward
- Intraday approval
- Number of intraday confirmations
- Retest confirmation
- Entry mode bonus

Entry mode bonuses:

```text
RETEST    +25
BREAKOUT  +20
MOMENTUM  +15
PULLBACK  +10
STANDARD  +5
```

Only the top-ranked candidates are alerted when `RANK_TOP_ALERTS_ONLY=True`.

---

## 📲 Telegram Alerts

Example alert:

```text
🟢 BREAKOUT CALL SETUP: NVDA
━━━━━━━━━━━━━━━
📅 Day: 2026-05-03
💰 Price: $510.25
⭐ Rule Score: 86/100
🏅 Rank Score: 158.4
🎯 Mode: BREAKOUT — Breakout with volume and intraday confirmation
🤖 AI: BUY (88%)
🏆 Quality: A | Timing: EARLY
📊 Intraday: 3/2 | Approved

🎯 Entry: 510.25
🛑 Stop: 501.20
🚀 Target: 528.90
📐 R/R: 2.1:1
```

If Telegram is not configured, alerts are printed to the console.

---

## 🗂️ Logging and Outcome Tracking

Alerts are logged to:

```text
stock_technical_alerts.csv
```

Logged fields include:

- Ticker
- Direction
- Entry mode
- Rule score
- Ranking score
- AI verdict
- AI confidence
- Entry / stop / target
- Risk/reward
- Intraday confirmation details
- Market bias
- Technical context
- Setup reasons

The bot also supports post-alert outcome tracking using minute bars.

---

## 📁 Main Files

| File | Purpose |
|---|---|
| `main.py` | Main launcher. Runs the advanced `StockTechnicalAIBot`. |
| `bot.py` | Bot orchestration, AI decision logic, entry modes, alerts, logging. |
| `bot_technical.py` | Polygon data fetching, technical indicators, scoring, market/sector logic. |
| `intraday_confirm.py` | Relaxed 5-minute confirmation engine. |
| `chart_capture.py` | TradingView screenshot capture using Playwright. |
| `bot_utils.py` | Formatting, safe parsing, AI JSON normalization. |
| `outcome_tracker.py` | Tracks post-alert outcomes. |
| `config.py` | Watchlists, thresholds, API keys, and runtime settings. |

---

## ⚙️ Installation

### 1. Clone the repo

```bash
git clone https://github.com/yamzalabhanu/StockeAlerts.git
cd StockeAlerts
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

If needed, install the main packages directly:

```bash
pip install polygon-api-client openai playwright requests pandas numpy
playwright install
```

---

## 🔑 Environment Variables

Set these before running:

```bash
export POLYGON_API_KEY="your_polygon_key"
export OPENAI_API_KEY="your_openai_key"
export TELEGRAM_TOKEN="your_telegram_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

Optional: copy `.env.example` to `.env` if you use a dotenv loader.

---

## ▶️ Run the Bot

```bash
python main.py
```

Expected startup:

```text
🚀 Stock Technical AI Bot Running
```

---

## ⏱️ Trading Windows

The bot only scans during configured quality trading windows:

```text
09:30–12:30 ET
13:30–15:30 ET
```

Outside those windows, you will see:

```text
⏸ Outside quality market window | sleeping 600s
```

This is expected behavior.

---

## 🧪 Testing Outside Market Hours

For debugging only, you can temporarily bypass the market-window check in `bot.py`, or adjust `QUALITY_WINDOWS` in `config.py`.

Do not use weekend or after-hours output as real trade signals because live stock/options liquidity is unavailable.

---

## ⚠️ Important Notes

- This bot is for alerts and research, not guaranteed profit.
- It does not trade automatically unless you add broker integration.
- Stock/options markets are closed on weekends.
- Weekend runs use stale data and should only be used for debugging/backtesting.
- Keep API keys out of public commits.

---

## 🚀 Future Enhancements

Planned upgrades:

- Performance dashboard
- Backtesting and replay mode
- Market regime adaptive scoring
- Auto-learning scoring adjustments
- Broker integration
- Cloud deployment with restart monitoring

---

## Author

Developed by Bhanu Yamzala.
