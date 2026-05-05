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

- Auto trading (Alpaca)
- News sentiment
- Database logging
- Cloud deployment

---

## 👨‍💻 Author

Bhanu Yamzala
