# 🚀 StockeAlerts — Advanced Intraday Stock & Options Alert Bot

StockeAlerts is an advanced intraday stock and options alert system that combines:

- Rule-based technical scoring
- 5-minute intraday confirmation
- Smart entry-mode detection
- OpenAI trade-quality filtering
- TradingView chart screenshot validation
- Telegram alerts
- CSV logging and outcome tracking

---

# 🏗️ Architecture Diagrams (NEW)

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

- Feature extraction (EMA, VWAP, Volume, Trend)
- Intraday confirmations
- AI scoring
- Risk/Reward validation
- Final decision (BUY / WAIT)

---

## 🔁 Symbol Handling Pipeline

![Symbol Pipeline](https://via.placeholder.com/1200x600.png?text=Symbol+Normalization+Pipeline)

```
Raw Symbol
   ↓
normalize_symbol()
   ↓
is_valid_symbol()
   ↓
Exchange Mapping
   ↓
TradingView Candidates
   ↓
Chart Capture (fallback enabled)
```

---

## 📊 Trading Decision Engine

![Decision Engine](https://via.placeholder.com/1200x600.png?text=Trading+Decision+Engine)

- Pullback / Breakout detection
- Volume + liquidity filters
- ETF alignment
- Market regime adjustment
- Final ranking

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

## 🎯 Entry Modes

- BREAKOUT
- RETEST
- MOMENTUM
- PULLBACK (A+ quality filtered)

---

## ▶️ Run the Bot

```bash
python main.py
```

---

## 👨‍💻 Author

Bhanu Yamzala
