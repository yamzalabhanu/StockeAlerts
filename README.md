# 🚀 StockeAlerts — AI/ML Multi-Strategy Trading Platform

StockeAlerts is an advanced AI-driven trading platform combining:

- ⚡ Intraday scalping engine
- 📈 Professional swing trading engine
- 🧠 Multi-layer AI + ML scoring
- 🔢 Fibonacci confluence trading
- 📊 Multi-timeframe confirmation
- 🤖 AI chart validation
- 📬 Telegram alerts
- 🔁 Backtesting + replay
- 📈 Adaptive learning
- 📊 Streamlit dashboard

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
- Momentum quality

### ✔ Adaptive score boosts

```text
Strong RSI → Boost
Strong Volume → Boost
Strong Trend → Boost
Strong Relative Strength → Boost
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
- Momentum structure

### Example

```text
Base Score: 78
ML Adjusted Score: 86
Win Probability: 0.74
```

---

# 📈 Professional Swing Trading Engine (MAJOR UPGRADE 🔥)

The swing engine was upgraded from a simple EMA/DMA scanner into a professional multi-factor confluence system.

---

## ✔ Advanced Swing Confirmation Engine

Swing trades now validate:

### ✅ Trend Structure

- 20 EMA
- 50 EMA
- 200 SMA
- EMA alignment
- Long-term trend direction

---

### ✅ RSI Momentum Engine

Uses:

- RSI 55–70 bullish zone
- RSI bounce zones
- Overextended detection
- Momentum continuation

---

### ✅ Institutional Volume Analysis

Confirms:

- 1.5x–3x volume spikes
- Breakout participation
- Weak low-volume moves
- Institutional accumulation

---

### ✅ MACD Momentum Engine

Validates:

- MACD crossover
- Histogram direction
- Zero-line momentum
- Trend acceleration

---

### ✅ ADX Trend Strength

Detects:

- Strong trends
- Weak/choppy markets
- Trend continuation probability

---

### ✅ Breakout + Retest Detection

One of the highest-probability swing setups:

```text
Breakout
   ↓
Retest
   ↓
Hold
```

---

### ✅ Relative Strength vs Market

Compares stock performance against:

- SPY
- QQQ
- Sector ETFs

Used to identify:

```text
Institutional accumulation
```

---

## 🧠 Multi-Timeframe Swing Confirmation (NEW 🔥)

Swing trades now require:

| Timeframe | Purpose |
|---|---|
| 📅 Weekly | Overall trend |
| 📊 Daily | Setup structure |
| ⏱️ 4H | Entry timing |

---

## ✔ Multi-Timeframe Logic

### Weekly Chart

Used for:

- macro trend direction
- institutional trend confirmation

### Daily Chart

Used for:

- breakout structure
- EMA alignment
- setup quality

### 4H Chart

Used for:

- entry timing
- pullback quality
- momentum confirmation

---

## ✔ Timeframe Conflict Detection

System penalizes:

```text
Weekly bullish
Daily bearish
4H weak
```

This dramatically reduces:

- fake breakouts
- countertrend trades
- low-quality setups

---

# 📊 Swing Alert Example

```text
🟢 SWING CALL SETUP: MSFT

Hold: 2-10 days
Entry: 421.50
Stop: 408.00
Target: 455.00
ML Probability: 0.72

Reasons:
- weekly trend bullish
- breakout retest hold
- RSI ideal bullish zone
- institutional volume
- MACD bullish cross
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
- Support/resistance

---

# 🎯 Smart Entry Engine

Entries require:

- Fib zone alignment
- Reclaim/rejection confirmation
- Volume confirmation
- Trend alignment
- Risk/reward validation
- Multi-timeframe alignment

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
Confluence Validation
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
Professional Swing Scanner
        ↓
Multi-Timeframe Confirmation
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
- swing vs intraday performance

---

# 🔁 Backtesting & Replay

## Features

- Historical replay
- Outcome tracking
- ML retraining
- Setup optimization
- Adaptive learning
- Swing trade analysis

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

## 🌎 Market Regime Intelligence (HIGH PRIORITY)

Detect:

- trending markets
- choppy conditions
- volatility expansion
- risk-on / risk-off regimes

Then dynamically adapt:

- scoring
- stop size
- aggressiveness
- allowed setups

---

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
