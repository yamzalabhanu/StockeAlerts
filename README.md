# StockeAlerts

StockeAlerts is an intraday stock alert bot that combines **rule-based technical scoring** with an **AI trade-quality filter** to decide whether to send trade alerts.

## What features are included

### 1) Intraday technical scanning engine
- Scans a configurable watchlist of tickers on a timed loop.
- Pulls minute/daily data from Polygon and computes key technical context per symbol.
- Caches technical snapshots for short intervals to reduce repeated API calls.

### 2) Static + auto-generated watchlist
- Supports a large base watchlist configured in `config.py`.
- Can automatically expand the watchlist using Polygon market snapshot movers.
- Auto-watchlist filters by minimum price, minimum volume, and minimum daily % move.

### 3) Multi-indicator context calculation
- Computes/uses:
  - VWAP
  - EMA 9 / EMA 21 / EMA 50
  - DMA 20 / DMA 50 / DMA 200
  - ATR(14)
  - ORB (opening range breakout) high/low
  - Premarket high/low
  - Previous-day high/low
  - 5m and 15m trend states

### 4) Strategy-quality gates and scoring logic
- Includes hard/soft filters such as:
  - Retest requirement controls
  - Late breakout/chase risk checks
  - Support/resistance rejection logic
  - Failed breakout penalties
  - Relative strength and volume spike weighting
  - Continuation quality weighting
- Uses score thresholds for CALL/PUT candidate selection.
- Restricts alerts to configured high-quality trading windows.

### 5) A+ breakout requirement logic
- For highest quality setups, it enforces directional breakout context:
  - CALL A+ requires price above premarket high or previous-day high.
  - PUT A+ requires price below premarket low or previous-day low.

### 6) Market and sector confirmation
- Computes market bias using ETFs (SPY, QQQ, IWM, SMH).
- Supports optional requirement that the overall market bias agrees with setup direction.
- Maps symbols to sector ETFs (for example SMH/XLF/XLE/XLY) and checks confirmation vs direction.

### 7) AI decision layer (OpenAI)
- Uses an OpenAI chat-completions model to evaluate setup quality and timing.
- AI receives rich technical context and rule-score reasons.
- AI returns structured trade decision JSON:
  - BUY or WAIT verdict
  - Confidence
  - Entry / stop / target
  - Risk/reward
  - Setup quality (A+/A/B/LOW)
  - Entry timing (EARLY/IDEAL/LATE/CHOP)
  - Human-readable rationale
- If OpenAI is unavailable, bot falls back to a deterministic rule-based decision with ATR plan.

### 8) Chart-capture + vision-assisted AI review
- Uses Playwright to open TradingView and capture a chart screenshot.
- Can send both chart image + technical context for AI evaluation.

### 9) Risk planning with ATR fallback
- Generates fallback trade plans from ATR multipliers:
  - ATR-based stop distance
  - ATR-based target distance
  - Computed risk/reward ratio

### 10) Alerting + delivery controls
- Sends alerts to Telegram (Markdown mode).
- If Telegram config is missing, messages are printed to console.
- Includes per-ticker, per-direction cooldown to prevent alert spam.
- Optionally ranks and limits top alerts per scan.

### 11) Persistent alert logging
- Appends every generated alert to CSV with extensive metadata:
  - Signal fields (direction, score, reasons)
  - AI fields (verdict, confidence, quality, timing, reasoning)
  - Trade plan values (entry/stop/target/RR)
  - Technical snapshot values (price, VWAP/EMAs/DMAs/ATR, levels, volume, trends)
  - Market bias details

### 12) Outcome tracking for post-trade analytics
- Tracks each alert’s 60-minute forward outcome using minute bars.
- Detects whether target or stop was hit first.
- Labels outcomes (WIN/LOSS/MIXED/OPEN_OR_BREAKEVEN).
- Logs maximum favorable/adverse excursion percentages to CSV.

## Main files
- `run.py` — entry point that starts the async bot.
- `bot.py` — bot orchestration, AI integration, logging, and alert flow.
- `bot_technical.py` — technical data fetching, signal helpers, trend/bias logic.
- `bot_utils.py` — utility functions and AI JSON normalization.
- `chart_capture.py` — TradingView screenshot capture.
- `outcome_tracker.py` — post-alert performance tracking.
- `config.py` — all runtime settings, thresholds, keys, and watchlists.

## Note
- API keys/tokens currently appear directly in `config.py`. In production, move them to environment variables or a secure secret manager.
