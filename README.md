# 🚀 StockeAlerts — AI/ML Multi-Strategy Trading Platform

StockeAlerts is an AI-assisted trading platform for intraday scalping, swing trading, options selection, price projection, setup scoring, Telegram alerts, adaptive learning, and performance review.

> ⚠️ Educational/research tool only. This project does not provide financial advice, and all generated signals must be reviewed before use.

---

## 🆕 Latest Platform Updates

### 🎯 2-Day Price Projection Engine

StockeAlerts now includes a dedicated short-term projection layer that estimates the next 2-day directional bias and expected price range.

The projection engine evaluates:

- Current price and ATR-based expected movement
- RSI momentum
- ADX trend strength
- Relative volume participation
- Market regime context
- Multi-timeframe alignment
- AI chart-structure quality

Projection output includes:

| Field | Meaning |
|---|---|
| `direction` | BULLISH, BEARISH, or SIDEWAYS |
| `confidence` | 50–95 confidence score |
| `projected_move_pct` | ATR-derived low/high move estimate |
| `expected_price_range` | Projected price range for the next move |
| `hold_guidance` | Continuation, downside-risk, or consolidation guidance |
| `risk` | LOW, MEDIUM, or HIGH projection risk |

Example:

```text
Direction: BULLISH
Confidence: 82
Projected Move: 1.8% - 3.7%
Expected Range: 428.40 - 436.25
Guidance: Likely continuation for 2-4 days.
Risk: LOW
```

---

### 📚 Projection Learning

Projection results can be recorded and compared against actual future price movement.

The learning layer tracks:

- Projected direction
- Confidence score
- Expected move range
- Entry price
- Actual move percentage
- Whether the projected direction was correct
- Projection accuracy after enough samples

This creates a feedback loop for evaluating whether the projection engine is directionally useful over time.

---

### 🧠 Unified AI Reasoning Engine

A new reasoning layer combines market context, setup quality, chart structure, multi-timeframe alignment, execution quality, and historical setup performance into a single report.

The reasoning engine now produces:

- Final adjusted score
- A+/A/WATCH/REJECT decision
- Market regime classification
- Multi-timeframe structure result
- Execution-quality result
- Setup-quality result
- Chart-structure quality
- Reasons, warnings, and rejection notes
- Historical learning context
- Human-readable narrative summary

---

### 🌎 Market Regime Intelligence

Market-regime detection is now an active scoring layer instead of only a planned feature.

Supported regimes include:

- `TRENDING_BULL`
- `TRENDING_BEAR`
- `CHOPPY`
- `HIGH_VOL`
- `LOW_VOL`
- `MIXED`

The engine uses ETF breadth, bias, ADX, VIX, and ATR expansion when available. Trending regimes can boost aligned breakout/momentum/retest setups, while choppy or high-volatility regimes tighten filtering and penalize low-quality chase trades.

---

### ⚡ Execution Quality Layer

Before a setup is promoted, the system can evaluate execution risk using liquidity and movement-quality inputs such as:

- Spread quality
- Relative volume
- Dollar volume
- ATR percentage
- Slippage risk
- Late breakout risk
- VWAP/EMA extension

Poor liquidity or poor execution quality can reduce scores or reject otherwise strong-looking setups.

---

### 🧱 Smart Money Concepts (SMC) Confirmation

StockeAlerts includes an optional Smart Money Concepts confirmation module for directional setups.

It checks for:

- Liquidity sweeps
- Fair value gaps
- Order-block zones
- VWAP/EMA directional alignment
- Volume imbalance

A setup is approved only when the SMC score is strong enough and structure aligns with the selected direction.

---

### 📈 Options Contract Selection + Theta Control

Options support has been expanded with a Polygon snapshot-based selector that can identify liquid near-the-money contracts.

The options layer evaluates:

- Expiration / DTE
- Strike proximity
- Bid / ask / mid
- Spread percentage
- Delta
- Theta
- Implied volatility
- Volume and open interest

Theta risk control can recommend trimming or exiting contracts when decay risk becomes elevated.

---

### 🧭 Trade Management AI

Open-trade management now evaluates whether to hold, trim, tighten stops, or exit based on trend and follow-through quality.

Inputs include:

- ADX trend strength
- Relative volume
- Market regime
- Multi-timeframe trend
- Candle follow-through
- Momentum reversal risk
- VWAP extension
- Unrealized R-multiple

---

### 📊 Daily Learning Report

The bot can generate a daily adaptive-learning report summarizing:

- Overall win rate
- Forecast accuracy
- Confidence adjustment
- Score adjustment
- Strongest setup structures
- Weak structures that should be penalized

This report helps the system prioritize setups with realized edge instead of only static technical rules.

---

# ⚡ Dual-Mode Trading Engine

StockeAlerts supports both intraday and swing workflows:

| Mode | Purpose |
|---|---|
| ⚡ Intraday | Same-day scalps using 5m / 15m structure |
| 📈 Swing Trading | Multi-day trend trades, typically 2–10 days |

---

# 🧠 Multi-Layer AI + ML System

## 4-Layer Intelligence Stack

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

## Setup-Based ML Learning

The system continuously learns:

- Which setup types perform best
- Win rate by entry mode
- Forecast accuracy by setup structure
- Adaptive score adjustments
- Priority boosts for historically strong structures

Supported setup types:

- BREAKOUT
- RETEST
- MOMENTUM
- PULLBACK
- SWING

---

## Feature-Based ML

The system analyzes:

- RSI behavior
- Relative volume
- Trend strength
- VWAP positioning
- EMA structure
- Momentum quality
- Risk/reward quality
- Intraday confirmations

Adaptive score examples:

```text
Strong RSI → Boost
Strong Volume → Boost
Strong Trend → Boost
Strong Relative Strength → Boost
Weak historical edge → Penalty
```

---

## Logistic Regression Probability Model

The sklearn model predicts the probability of trade success using features such as:

- Technical score
- Risk/reward ratio
- Price vs VWAP
- Price vs EMA21
- Trend alignment
- Volume participation
- Intraday confirmations
- Momentum structure

Example:

```text
Base Score: 78
ML Adjusted Score: 86
Win Probability: 0.74
```

---

# 📈 Professional Swing Trading Engine

The swing engine is a multi-factor confluence system for CALL and PUT swing setups.

## Advanced Swing Confirmation

Swing trades validate:

### Trend Structure

- 20 EMA
- 50 EMA
- 200 SMA
- EMA alignment
- Long-term trend direction

### RSI Momentum

- RSI 55–70 bullish zone
- RSI bounce zones
- Overextended detection
- Momentum continuation

### Institutional Volume

- 1.5x–3x volume spikes
- Breakout participation
- Weak low-volume moves
- Institutional accumulation

### MACD Momentum

- MACD crossover
- Histogram direction
- Zero-line momentum
- Trend acceleration

### ADX Trend Strength

- Strong trends
- Weak/choppy markets
- Trend continuation probability

### Breakout + Retest Detection

```text
Breakout
   ↓
Retest
   ↓
Hold
```

### Relative Strength vs Market

Compares stock performance against market and sector context to find institutional accumulation or relative weakness.

---

## Multi-Timeframe Swing Confirmation

| Timeframe | Purpose |
|---|---|
| Weekly | Overall trend |
| Daily | Setup structure |
| 4H | Entry timing |

The engine penalizes conflicts such as:

```text
Weekly bullish
Daily bearish
4H weak
```

This helps reduce fake breakouts, countertrend trades, and low-quality swing entries.

---

# 📊 Alert Examples

## Intraday Alert Contents

Intraday alerts can include:

- Entry mode and direction
- AI score and ranking score
- AI confidence with historical adjustment
- Setup quality and timing
- ETF/market bias
- Intraday confirmation count
- Historical win rate and forecast accuracy
- Entry, stop, target, and risk/reward
- VWAP, EMA, ORB, premarket, and prior-day levels
- Retest status and late-breakout risk
- Rule reasons and AI narrative

## Swing Alert Example

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

## Fibonacci Retracement

- 38.2%
- 50%
- 61.8%

## Fibonacci Extensions

- 1.272 → Partial profit
- 1.618 → Final exit

## Multi-Timeframe Confluence

Fib levels are validated against:

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
- Setup-quality filters
- Chart-structure validation
- Execution-quality validation

---

# 💰 Risk Management System

## Dynamic Position Sizing

Automatically calculates:

- Position size
- Risk per trade
- Stop placement
- Capital exposure

## Smart Exit System

- Partial profit taking
- ATR trailing stop
- Dynamic RR management
- Multi-target exits
- Theta-risk checks for options
- AI-assisted hold/trim/exit recommendations

---

# 📊 Full Trading Lifecycle

```text
Watchlist Scan
      ↓
Technical Analysis
      ↓
Intraday Engine + Swing Engine
      ↓
Market Regime Detection
      ↓
Multi-Timeframe + Setup Quality Filters
      ↓
AI Reasoning + ML Scoring
      ↓
Price Projection
      ↓
Probability + Historical Calibration
      ↓
Risk / Execution / Options Review
      ↓
Telegram Alerts
      ↓
Dashboard Logging
      ↓
Outcome Tracking
      ↓
Adaptive Learning + Daily Report
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
Market Regime Intelligence
        ↓
Multi-Timeframe Confirmation
        ↓
Execution + Setup Quality Filters
        ↓
AI Reasoning Engine
        ↓
ML Scoring Layers
        ↓
Price Projection Engine
        ↓
Sklearn Probability Model
        ↓
Trade Ranking Engine
        ↓
Telegram + Dashboard
        ↓
Outcome Tracking + Adaptive Learning
```

---

# 📊 Dashboard Features

The Streamlit dashboard tracks:

- Alerts
- ML probabilities
- Win/loss statistics
- Setup performance
- Replay analysis
- Ranking scores
- Swing vs intraday performance
- Setup quality distribution
- Historical forecast accuracy fields when available

---

# 🔁 Backtesting, Replay & Learning

Features:

- Historical replay
- Outcome tracking
- ML retraining
- Setup optimization
- Adaptive learning
- Swing trade analysis
- Projection-vs-actual comparison
- Daily learning reports

---

# 🔧 Installation

```bash
pip install -r requirements.txt
pip install scikit-learn
pip install streamlit
```

Optional browser setup for chart capture:

```bash
playwright install chromium
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

# 🔁 Train / Refresh Learning Models

```bash
python backtest_replay.py
python daily_report_engine.py
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

## 💵 Live PnL Dashboard

- Real-time PnL
- Trade analytics
- Win rate by setup
- Daily/weekly performance

## 🤖 Auto Trading (Alpaca)

- Automated execution
- Smart order routing
- Dynamic position sizing
- Stop/target automation

## 📰 AI Sentiment Engine

- News sentiment
- Twitter/X analysis
- Earnings reaction analysis
- Macro event filtering

## ☁️ Cloud Deployment

- Render deployment
- Docker support
- Multi-worker scanning
- API service mode

---

# ⚠️ Notes

- Requires historical logs for ML improvement.
- Works best during active market sessions.
- Swing analysis can run after hours.
- Price projections are probabilistic estimates, not guarantees.
- Not financial advice.

---

# 👨‍💻 Author

Bhanu Yamzala
