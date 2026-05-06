# 🚀 StockeAlerts — AI/ML Multi-Strategy Trading Platform

StockeAlerts is an advanced AI-driven trading platform combining:

- Intraday scalping engine
- Swing trading engine
- Multi-layer ML scoring
- Fibonacci confluence trading
- AI chart validation
- Telegram alerts
- Backtesting + replay
- Adaptive learning
- Streamlit dashboard

---

# 🆕 2026 Major Enhancements

## ⚡ Dual-Mode Trading Engine

StockeAlerts now supports BOTH:

| Mode | Purpose |
|---|---|
| ⚡ Intraday | Same-day scalps using 5m / 15m structure |
| 📈 Swing Trading | Multi-day trend trades (2–10 days) |

---

# 🧠 Multi-Layer AI + ML System

## ✔ 4-Layer Intelligence Stack

```text
Rule-Based Technical Score
            ↓
Setup-Based ML Learning
            ↓
Feature-Based ML (RSI / Volume / Trend)
            ↓
Sklearn Logistic Regression Probability Model
```

---

## 🤖 Setup-Based ML Learning

System continuously learns:

- Which setup types perform best
- Win-rate by entry mode
- Adaptive score adjustments

### Supported Setup Types

- BREAKOUT
- RETEST
- MOMENTUM
- PULLBACK
- SWING

---

## 📊 Feature-Based ML

System analyzes:

- RSI behavior
- Relative volume
- Trend strength
- VWAP positioning
- EMA structure

### ✔ Adaptive score boosts

```text
Strong RSI → Boost
Strong Volume → Boost
Strong Trend → Boost
```

---

## 🧠 Logistic Regression Probability Model (Sklearn)

### ✔ Real ML Probability Prediction

The model predicts:

```text
Probability of trade success
```

### Uses Features Like:

- Technical score
- Risk/reward ratio
- Price vs VWAP
- Price vs EMA21
- Trend alignment
- Volume participation
- Intraday confirmations

### Example

```text
Base Score: 78
ML Adjusted Score: 86
Win Probability: 0.74
```

---

# 📈 Swing Trading Engine (NEW 🔥)

## ✔ Swing Trading Features

- Daily trend analysis
- DMA20 / DMA50 / DMA200 structure
- ATR-based stops and targets
- Pullback + breakout entries
- Multi-day holds (2–10 days)
- ML probability scoring
- Telegram swing alerts

---

## ✔ Swing Trade Conditions

### Bullish Swing Setup

- Price above DMA20 / DMA50
- DMA20 > DMA50
- Near recent highs
- Pullback to DMA20
- Strong volume

### Bearish Swing Setup

- Price below DMA20 / DMA50
- DMA20 < DMA50
- Near recent lows
- Bearish rejection
- Strong volume

---

## 📊 Swing Alert Example

```text
🟢 SWING CALL SETUP: MSFT

Hold: 2-10 days
Entry: 421.50
Stop: 408.00
Target: 455.00
ML Probability: 0.72
```

---

# 🧠 Fibonacci Trading Engine

## ✔ Fibonacci Retracement

- 38.2%
- 50%
- 61.8%

## ✔ Fibonacci Extensions

- 1.272 → Partial Profit
- 1.618 → Final Exit

## ✔ Multi-Timeframe Confluence

Fib levels validated against:

- VWAP
- EMA21
- ORB
- Premarket levels
- Previous day highs/lows
- Swing structure

---

# 🎯 Smart Entry Engine

Entries require:

- Fib zone alignment
- Reclaim/rejection confirmation
- Volume confirmation
- Trend alignment
- Risk/reward validation

---

# 💰 Risk Management System

## ✔ Dynamic Position Sizing

Automatically calculates:

- position size
- risk per trade
- stop placement
- capital exposure

---

## ✔ Smart Exit System

- Partial profit taking
- ATR trailing stop
- Dynamic RR management
- Multi-target exits

---

# 📊 Full Trading Lifecycle

```text
Watchlist Scan
      ↓
Technical Analysis
      ↓
Intraday Engine + Swing Engine
      ↓
AI + ML Scoring
      ↓
Probability Validation
      ↓
Risk Management
      ↓
Telegram Alerts
      ↓
Dashboard Logging
      ↓
Adaptive Learning
```

---

# 🏗️ System Architecture

```text
Market Data APIs
        ↓
Technical Analysis Engine
        ↓
Fib + Confluence Engine
        ↓
Intraday Scanner
        ↓
Swing Scanner
        ↓
ML Scoring Layers
        ↓
Sklearn Probability Model
        ↓
Trade Ranking Engine
        ↓
Telegram + Dashboard
```

---

# 📊 Dashboard Features

## Streamlit Dashboard

Tracks:

- alerts
- ML probabilities
- win/loss statistics
- setup performance
- replay analysis
- ranking scores

---

# 🔁 Backtesting & Replay

## Features

- Historical replay
- Outcome tracking
- ML retraining
- Setup optimization
- Adaptive learning

---

# 🔧 Installation

```bash
pip install -r requirements.txt
pip install scikit-learn
pip install streamlit
```

---

# ▶️ Run Bot

```bash
python main.py
```

---

# 📊 Run Dashboard

```bash
streamlit run streamlit_dashboard.py
```

---

# 🔁 Train ML Models

```bash
python backtest_replay.py
```

---

# 🔑 Environment Variables

```text
OPENAI_API_KEY=
POLYGON_API_KEY=
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
```

---

# 🚀 Next Planned Upgrades

## 📈 Portfolio & Position Management

- Open position tracking
- Portfolio exposure management
- Risk balancing
- Sector concentration limits

---

## 💵 Live PnL Dashboard

- Real-time PnL
- Trade analytics
- Win-rate by setup
- Daily/weekly performance

---

## 🤖 Auto Trading (Alpaca)

- Automated execution
- Smart order routing
- Dynamic position sizing
- Stop/target automation

---

## 🌎 Market Regime Intelligence

- Bull/bear/chop detection
- Strategy adaptation
- Volatility-aware scoring

---

## 📰 AI Sentiment Engine

- News sentiment
- Twitter/X analysis
- Earnings reaction analysis
- Macro event filtering

---

## ☁️ Cloud Deployment

- Render deployment
- Docker support
- Multi-worker scanning
- API service mode

---

# ⚠️ Notes

- Requires historical logs for ML improvement
- Works best during active market sessions
- Swing analysis can run after-hours
- Not financial advice

---

# 👨‍💻 Author

Bhanu Yamzala
