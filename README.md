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

## 🧠 Multi-Layer ML Trading Engine (NEW 🔥)

### ✔ 3-Level Intelligence System

```
Rule-Based Score
   ↓
Setup-Based ML (win-rate learning)
   ↓
Feature-Based ML (RSI, Volume, Trend)
   ↓
Sklearn Logistic Regression (Probability Model)
```

---

## 🤖 Feature-Based ML (RSI / Volume / Trend)

System learns ideal conditions from winning trades:

- RSI behavior
- Relative volume patterns
- Trend strength

### ✔ Adaptive Boosting

- Strong RSI zone → score boost
- High volume → score boost
- Strong trend → score boost

---

## 🧠 Sklearn Logistic Regression Model (NEW 🚀)

### ✔ Predicts Trade Success Probability

Model uses:

- Technical score
- Risk/Reward ratio
- Volume vs average volume
- Price vs VWAP / EMA21
- 5m / 15m trend alignment

### ✔ Output

```text
Probability of trade success (0 → 1)
```

### ✔ Integrated into scoring

- Score dynamically adjusted
- Probability stored per trade

---

## 📊 Example

```text
Base Score: 78
ML Adjusted Score: 85
Win Probability: 0.72
```

---

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
- Intraday swing
- Previous day high/low

---

## 🎯 Entry Timing Engine

Entries must satisfy:
- Inside Fibonacci zone
- Strong reclaim/rejection candle
- Minimum confirmations (≥ 3)

---

## 💰 Dynamic Risk Management

- Position sizing based on stop distance
- Fixed risk per trade (1%)
- Capital protection logic

---

## 📊 Smart Exit Strategy

- TP1 → 1.272 (partial exit)
- TP2 → 1.618 (final exit)
- Trailing stop after TP1

---

## 🧠 Full Trade Lifecycle

```
Scan → A+ Setup → Entry (Fib Zone)
   ↓
ML Scoring + Probability
   ↓
Position Size (Risk-based)
   ↓
TP1 → Partial Exit
   ↓
Trailing Stop
   ↓
TP2 → Final Exit
```

---

## 🔥 System Capabilities

- Institutional-grade confluence trading
- Self-learning adaptive scoring
- Feature-driven ML intelligence
- Probability-based trade filtering
- Risk-managed execution

---

# 🏗️ Architecture

```
Watchlist → Data Fetch → Technical Analysis
        ↓
Fib + Confluence Engine
        ↓
ML Scoring (3 layers)
        ↓
Probability Model (Sklearn)
        ↓
Trade Decision → Alerts / Execution
```

---

## 🔧 Setup

```bash
pip install -r requirements.txt
pip install scikit-learn
```

---

## ▶️ Run

```bash
python main.py
```

---

## 🔁 Train ML Models

```bash
python backtest_replay.py
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

- Requires historical data for ML improvement
- Works best with continuous logging
- Not financial advice

---

## 🚀 Future Enhancements

- Auto-trading (Alpaca integration)
- Live PnL dashboard
- News + sentiment ML
- Cloud deployment

---

## 👨‍💻 Author

Bhanu Yamzala
