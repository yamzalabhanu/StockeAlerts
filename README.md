# 🚀 StockeAlerts — Advanced Intraday Stock & Options Alert Bot

StockeAlerts is an advanced intraday trading system combining:

- Rule-based technical scoring
- Intraday confirmation (5m / 15m)
- AI-based decision engine
- A+ setup filtering
- Adaptive learning
- TradingView chart validation
- Telegram alerts
- Backtesting & dashboard

---

# 🆕 Latest Feature Enhancements (2026 Upgrade)

## 🧠 Fibonacci Trading System (Pro-Level)

### ✔ Retracement Levels
- 38.2%
- 50%
- 61.8%

### ✔ Extension Targets
- 1.272 → Partial Profit
- 1.618 → Final Exit

### ✔ Confluence Logic
A trade is valid ONLY when Fib aligns with:
- EMA21 / VWAP
- ORB levels
- Premarket levels
- Previous day high/low
- Recent swing levels

---

## 🔁 Multi-Timeframe Confluence

System validates Fib across:
- Intraday swing (current timeframe)
- Higher timeframe proxy (Previous Day High/Low)

---

## 🎯 Entry Timing Engine

Entries must satisfy:
- Inside Fibonacci zone
- Strong reclaim/rejection candle
- Minimum confirmations (≥ 3)

This prevents:
- Early entries
- Late chasing
- Weak pullbacks

---

## 💰 Dynamic Risk Management

### ✔ Position Sizing
- Based on stop-loss distance
- Fixed risk per trade (1%)

### ✔ Configuration
- Account size configurable
- Max position cap supported

---

## 📊 Smart Exit Strategy

### ✔ Partial Profit Taking
- 50% exit at 1.272 Fib

### ✔ Final Target
- Remaining exit at 1.618 Fib

### ✔ Trailing Stop Logic
After TP1:
- Stop moves to EMA21 or breakeven
- Locks profit and reduces risk

---

## 🧠 Full Trade Lifecycle

```
Scan → A+ Setup → Entry (Fib Zone)
   ↓
Position Size (Risk-based)
   ↓
TP1 → 1.272 (partial exit)
   ↓
Stop → Trail to EMA21 / BE
   ↓
TP2 → 1.618 (final exit)
```

---

## 🔥 Resulting System Capabilities

- Institutional-grade pullback detection
- Multi-factor confluence filtering
- Precision entry timing
- Dynamic position sizing
- Structured profit-taking
- Risk-controlled trade management

---

# 🏗️ Architecture Diagrams

## 🔄 End-to-End Flow

![Architecture](https://via.placeholder.com/1200x600.png?text=Trading+System+Architecture)

```
Watchlist → Symbol Engine → Data Fetch → Technical Analysis
        ↓
Intraday Confirmation → Entry Mode Detection
        ↓
AI Scoring → A+ Filtering → Market Regime
        ↓
Ranking Engine → Alerts / Execution / Logging
```

---

## 🧠 AI Decision Pipeline

![AI Pipeline](https://via.placeholder.com/1200x600.png?text=AI+Decision+Pipeline)

- Feature extraction (EMA, VWAP, Volume)
- Intraday confirmation
- AI scoring
- Risk/Reward validation
- Final decision

---

## 🔁 Symbol Handling Pipeline

![Symbol Pipeline](https://via.placeholder.com/1200x600.png?text=Symbol+Normalization+Pipeline)

```
Raw Symbol → normalize_symbol() → is_valid_symbol()
        ↓
Exchange Mapping → TradingView Candidates
        ↓
Chart Capture (fallback retry)
```

---

## 🔥 Core Features

### 🧠 A+ High Win-Rate Mode
- Pullback ≥ 85
- Breakout ≥ 80
- Momentum ≥ 85

### 🎯 Entry Modes
- PULLBACK (EMA21/VWAP reclaim)
- BREAKOUT (level break + volume)
- MOMENTUM (continuation)
- RETEST (true breakout retest)

### 📊 Technical Indicators
- VWAP
- EMA 9 / 21 / 50
- DMA 20 / 50 / 200
- ATR
- ORB levels
- Premarket / Previous day levels

---

## 🧠 AI Engine

Uses OpenAI to evaluate:
- Setup quality
- Risk/reward
- Entry timing
- Market context

Outputs structured JSON decision.

---

## 📊 Dashboard

```bash
streamlit run streamlit_dashboard.py
```

---

## 🔁 Backtesting

```bash
python backtest_replay.py
```

---

## ▶️ Run

```bash
python main.py
```

---

## ⚙️ Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install
```

---

## 🔑 Environment Variables

```
OPENAI_API_KEY=
POLYGON_API_KEY=
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## ⚠️ Notes

- Works only during market hours
- Not financial advice
- Requires API keys

---

## 🚀 Future Enhancements

- Full auto trading (Alpaca integration)
- Live PnL tracking
- Trade lifecycle dashboard
- News + sentiment integration
- Cloud deployment (24/7)

---

## 👨‍💻 Author

Bhanu Yamzala
