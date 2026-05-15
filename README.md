# 🚀 StockeAlerts — AI/ML Multi-Strategy Trading Platform

StockeAlerts is an AI-assisted trading platform for intraday scalping, swing trading, options selection, price projection, setup scoring, Telegram alerts, adaptive learning, and performance review.

> ⚠️ Educational/research tool only. This project does not provide financial advice, and all generated signals must be reviewed before use.

---

## 🆕 Latest Platform Updates

### 🧯 Daily Trade Cap + Fill-Aware Options Automation

Ranked alert delivery and automated option buys now share a market-local daily trade cap so the bot can finish a full scan, rank the best intraday/swing candidates, and still stop once the configured day limit is reached. The default cap is `10` trades per New York trading day, and the option order state keeps a per-day buy counter so restarted scans do not accidentally over-trade.

Paper options automation is also fill-aware. Buy submissions can be tracked as pending until Alpaca reports an actual fill, then the manager records the broker `filled_avg_price`, `filled_at` timestamp, and `buy_order_id`. Profit targets and stop losses are calculated from the actual filled premium instead of the submitted limit price, and Telegram updates call out when a pending buy starts being monitored from the resolved fill price.

Low-premium protection was tightened across both contract selection and order submission. The options selector rejects contracts below `MIN_OPTION_PREMIUM`, same-week fallback contracts must still pass that premium floor, and the order manager applies `MIN_OPTION_BUY_PREMIUM` before submitting a paper buy so sub-$0.50 contracts are skipped by default.

Key controls include:

| Setting | Purpose |
|---|---|
| `MAX_TRADES_PER_TRADING_DAY=10` | Market-local daily cap shared by ranked alert selection and option buy automation |
| `MIN_OPTION_PREMIUM=0.50` | Minimum option entry premium required by contract selection and fallback picks |
| `MIN_OPTION_BUY_PREMIUM=0.50` | Minimum option limit price accepted by the Alpaca paper order manager |
| `OPTION_PROFIT_TARGET_PCT=50` | Managed paper sell target measured from the actual filled premium |
| `OPTION_STOP_LOSS_PCT=-50` | Managed paper stop measured from the actual filled premium |
| `OPTION_ORDER_STATE_FILE=option_order_state.json` | Persists open/pending option positions, fill metadata, and daily trade counts |

---

### 🧬 Swing Quality Blend + Relaxed Benchmark Gate

Swing scoring now blends classic trend/momentum checks with institutional-style price-action evidence before a candidate reaches AI reasoning. The scorer can add or subtract weight for HH/HL or LH/LL structure, 9/21/50 EMA stage alignment, pivot/base breakouts or breakdowns, volume dry-up during bases, VCP contraction, retest holds/rejections, gap intent, ATR extension risk, and failed reclaim/rejection behavior. This gives pullback, breakout, and breakdown swings a richer score than simple moving-average alignment alone.

The swing benchmark gate has also been tuned from an elite-only hard stop into a high-quality blended gate. It can now accept `A+` or `A` reasoning decisions, requires an `88` composite score and at least `1.8R`, allows `GOOD` or `WARNING` execution quality, allows `ELITE` or `GOOD` chart structure, and permits mixed-regime exceptions only for perfect-score `A+` setups. The gate still logs every miss so skipped swing candidates remain auditable.

Key benchmark defaults include:

| Setting | Purpose |
|---|---|
| `SWING_MIN_COMPOSITE_SCORE=88` | Minimum final AI/composite score for benchmark-quality swing alerts |
| `SWING_MIN_BENCHMARK_RR=1.8` | Minimum risk/reward accepted by the swing benchmark gate |
| `SWING_ALLOWED_DECISIONS=A+/A` | AI reasoning decisions eligible for swing alerts |
| `SWING_ALLOWED_CHART_STRUCTURES=ELITE/GOOD` | Vision chart grades accepted by the benchmark gate |
| `SWING_MIXED_REGIME_ELITE_SCORE=100` | Mixed-regime exception reserved for perfect-score `A+` swing setups |

---

### 🖼️ TradingView Chart Capture Symbol Fallbacks

Chart capture and AI vision now normalize symbols before opening TradingView and try a prioritized list of exchange-prefixed candidates (`NASDAQ`, `NYSE`, `AMEX`, plus ETF and NYSE overrides). If TradingView reports that a symbol is invalid, the capture layer automatically tries the next candidate before failing. This improves chart screenshots for NYSE names, ETFs, aliases such as `NASDAQ:ORCL`, and symbols that require exchange-specific TradingView routing.

---

### 🧭 Expanded Master Watchlist + Stricter Quality Windows

The scan universe now keeps the curated `CORE_WATCHLIST`, `SECONDARY_WATCHLIST`, and `SPEC_WATCHLIST` tiers, while also documenting the expanded `MASTER_WATCHLIST` used to track liquid ETFs, leveraged products, AI/semiconductor leaders, big tech, high-beta crypto/fintech names, biotech, energy, industrials, retail, travel, and other active movers. Intraday quality windows were tightened to the highest-opportunity parts of the day (`08:30-11:30` and `13:30-14:59` ET), and the default intraday alert threshold is now `95` so the ranked-alert flow favors cleaner A+ setups.

Key defaults include:

| Setting | Purpose |
|---|---|
| `INTRADAY_MIN_SCORE=95` | Baseline intraday quality floor before alerts are considered |
| `MIN_SCORE=95` | High-quality setup threshold for warning-tolerant intraday paths |
| `QUALITY_WINDOWS` | Preferred scan windows: morning momentum and early afternoon continuation |
| `MASTER_WATCHLIST` | Broad reference universe for ETFs, sectors, AI/semis, crypto beta, biotech, and active movers |

---

### 🌙 Extended-Hours Bias for Opening Alerts

Early-session scans can now score after-hours and pre-market price discovery before regular-session trend data is fully formed. When enabled, the bot looks for enough extended-hours volume and movement, adds directional bias weight when pre-market context agrees with the setup, and applies a conflict penalty when the opening alert fights the overnight/pre-market tape.

Key controls include:

| Setting | Purpose |
|---|---|
| `EXTENDED_HOURS_BIAS_ENABLED` | Enable pre-market/after-hours directional scoring, defaults to `true` |
| `EXTENDED_HOURS_BIAS_WEIGHT` | Score boost for aligned extended-hours context, defaults to `12` |
| `EXTENDED_HOURS_CONFLICT_PENALTY` | Penalty when the setup conflicts with extended-hours direction, defaults to `10` |
| `EXTENDED_HOURS_MIN_MOVE_PCT` | Minimum extended-hours move needed to count as directional context |
| `EXTENDED_HOURS_MIN_VOLUME` | Minimum extended-hours volume required before bias is trusted |

---

### 🏆 High-Quality Swing Benchmark Gate

Swing alerts now use a blended benchmark profile for high-quality swing trades. The benchmark accepts only `A+` or `A` reasoning decisions, an `88+` composite score, at least `1.8R` risk/reward, directional regime alignment or an elite mixed-regime exception, acceptable execution quality, good/strong multi-timeframe alignment, and `ELITE` or `GOOD` chart structure. The gate logs explicit rejection reasons for missed score, risk/reward, regime, execution, multi-timeframe, chart-structure, or AI-risk requirements so skipped candidates are easier to audit.

---

### 🌅 Early-Session Intraday Grace Filters

Opening-drive trades now get a dedicated early-session path so strong setups are not rejected just because the first candles have limited volume history, incomplete retest data, or still-forming execution context. Until `EARLY_SESSION_END_TIME` (default `10:30` New York time), the bot marks qualifying technical contexts with `early_session_setup`, allows lower relative-volume and confirmation minimums, and lets execution/setup quality return `WARNING` instead of hard rejection when the final score, AI gate, and risk/reward still justify the alert.

Key controls include:

| Setting | Purpose |
|---|---|
| `EARLY_SESSION_GRACE_ENABLED` | Enable the morning-session grace path, defaults to `true` |
| `EARLY_SESSION_END_TIME` | Cutoff for early-session handling, defaults to `10:30` ET |
| `EARLY_SESSION_MIN_SCORE_BUFFER` | Score buffer used when preserving strong morning candidates |
| `EARLY_SESSION_MIN_CONFIRMATIONS` | Minimum intraday confirmations during the grace window |
| `EARLY_SESSION_REL_VOLUME_MIN` | Relative-volume threshold during the grace window |

---

### 🏅 Ranked Alert Caps, ETF Buckets, and Daily De-Dupe

The scanner now evaluates the full watchlist first, ranks all high-quality candidates, and then sends only the best alerts from the completed scan. Intraday and swing candidates have separate caps, ticker-level de-dupe prevents repeat alerts for the same symbol on the same day, and ETF symbols are explicitly tracked so broad-market/sector alerts can be bucketed alongside stock picks instead of flooding the same scan.

Key controls include:

| Setting | Purpose |
|---|---|
| `MAX_INTRADAY_ALERTS_PER_SCAN` | Maximum intraday alerts per completed scan, defaults to `5` |
| `MAX_SWING_ALERTS_PER_SCAN` | Maximum swing alerts per completed scan, defaults to `5` |
| `MAX_HIGH_QUALITY_ALERTS_PER_SCAN` | Optional quieter global cap, clamped by the per-type caps |
| `MAX_TRADES_PER_TRADING_DAY` | Market-local daily cap for ranked trade alerts and option buys, defaults to `10` |
| `ETF_ALERT_SYMBOLS` | Built-in ETF/sector ETF bucket used by ranked alert selection |

---

### 🤖 Paper Options Auto-Trading Hardening

Recommended option contracts can now flow directly into Alpaca paper DAY limit orders when automation is enabled. The order manager normalizes Polygon/Massive symbols such as `O:SPY260515C00500000` into Alpaca-compatible OCC symbols, avoids duplicate open tracked positions, records state in `option_order_state.json`, and manages paper exits at the configured option premium profit target or stop loss. If Alpaca rejects an order or options access is unavailable, the scanner continues and sends a clear Telegram failure/skip message.

For near-term trading, the contract selector can fall back to same-week high-liquidity contracts when they pass the high-volume, open-interest, spread, IV, DTE, and minimum-premium guardrails, so paper orders can still be staged for actionable weekly contracts rather than failing because the default DTE window is too strict. The order manager also blocks duplicate tracked positions, low-premium orders, and buys that would exceed the daily trade cap.

Submitted option buys can be stored as `PENDING_FILL` until Alpaca returns a filled average price. Once the fill is available, monitoring switches to that broker-filled premium for both take-profit and stop-loss math.

---

### 🛡️ Outcome Tracking Entitlement Guard

Post-alert outcome tracking now detects Polygon authorization/entitlement failures and can skip additional outcome checks for the rest of the run. This keeps scans from repeatedly failing when minute-aggregate access is unavailable, while leaving CSV outcome recording and learning flows intact when data access is valid. Use `ENABLE_OUTCOME_TRACKING=false` to disable checks permanently or keep `OUTCOME_TRACKING_SKIP_UNAUTHORIZED=true` to auto-suppress follow-up checks after entitlement errors.

---

### 🧠 GPT-5 Mini Reasoning Defaults

AI-backed market analysis, alert gates, trade-management decisions, and chart-vision reads now default to `gpt-5-mini`. Reasoning-capable models are configured through a shared OpenAI options helper that passes `reasoning_effort` instead of forcing low-temperature chat behavior, while non-reasoning model overrides can still use temperature settings.

Key controls include:

| Setting | Purpose |
|---|---|
| `OPENAI_REASONING_MODEL` | Market-data reasoning model for AI alert decisions, defaults to `gpt-5-mini` |
| `OPENAI_REASONING_EFFORT` | Reasoning depth for GPT-5/o-series models, defaults to `medium` |
| `OPENAI_VISION_MODEL` | Chart-vision model override, defaults to the reasoning model |

---

### 👁️ AI Vision Chart Reader

StockeAlerts can capture TradingView screenshots and send the chart image to OpenAI Vision for a discretionary candle-structure read. The normalized visual reading can be attached to `tech["vision_chart"]` so chart-structure scoring, swing validation, and AI reasoning gates can account for visual context that numeric indicators often miss. The intraday prompt now forces an options-entry verdict of `A+ CALL`, `A+ PUT`, `WAIT`, or `REJECT` and avoids chasing breakouts already extended more than 1.5 ATR without a clean retest.

The vision reader evaluates:

- Failed breakouts and late chase risk
- Volatility compression before expansion
- Wedges and tightening structure
- Exhaustion candles and rejection wicks
- Trapped longs / trapped shorts
- Liquidity grabs above resistance or below support
- Overall trend quality: strong, healthy, mixed, choppy, or exhausted
- Market phase classification, retest confirmation, ETF alignment (`SPY`/`QQQ`/`SMH`/`VIX`), volume confirmation, and risk/reward viability
- ORB, premarket high/low, and previous-day high/low levels supplied in the technical context
- Multi-timeframe 1m/5m/15m screenshot stacks plus up to three prior screenshots for sequence memory

Example:

```python
from chart_ai import analyze_chart_vision, capture_multi_timeframe_charts

image_paths = await capture_multi_timeframe_charts("NASDAQ:NVDA", timeframes=("1", "5", "15"))
vision = await analyze_chart_vision(
    "NASDAQ:NVDA",
    analysis=tech,
    timeframe="1/5/15",
    image_paths=image_paths,
    screenshot_sequence=prior_three_chart_paths,
)
tech["vision_chart"] = vision
```

Required browser setup for screenshot capture:

```bash
playwright install chromium
```

---

### 🎯 High-Liquidity Options Contract Recommendations

The options selector now ranks contracts by actionable liquidity before simple moneyness convenience. It scans Polygon/Massive-compatible option snapshots, applies DTE, spread, IV, delta, volume, and open-interest guardrails, then prioritizes contracts with the strongest same-day volume, open interest, volume/OI participation, dollar volume, and recommendation score.

Exceptional same-day option volume can also override stale/low open interest and include near-term expirations, so alerts can recommend unusually active strikes such as a high-volume weekly call instead of a thinner contract. Tune this with `HIGH_VOLUME_OPTION_MIN_VOLUME` and `HIGH_VOLUME_OPTION_MIN_DTE`.

Telegram alerts can include a detailed recommended-contract block with contract symbol, side, strike, expiration, DTE, bid/ask/mid, spread percentage, volume/OI, recommendation score, delta, theta, IV, and an estimated delta-only contract move if the underlying reaches target.

---

### 📊 Telegram Predicted Move Alerts

Alert formatting now includes a compact predicted-price-move line that translates entry, stop, target, and direction into the expected underlying move and stop risk. When an option contract is attached, the alert also estimates the contract premium move using the contract mid price and delta.

---

### 🧾 Telegram Delivery Hardening

Telegram alerts are now sent through a safe HTML formatting path instead of relying on fragile Markdown parsing. Dynamic alert text is HTML-escaped first, simple bold labels are preserved, and the bot automatically retries with plain text if Telegram rejects a formatted payload. This prevents tickers, setup keys, URLs, underscores, ampersands, and model-generated notes from breaking alert delivery.

---

### 📌 Auto Watchlist + Extended-Hours / Options Discovery

The scanner can now merge the static watchlist with active Polygon daily movers, extended-hours movers, and option-activity names. When `USE_AUTO_WATCHLIST` is enabled, the bot pulls U.S. equity snapshots or historical grouped aggregates, checks Polygon minute bars for pre-market/after-hours volume and percentage movement, adds Polygon option snapshot volume/OI context, ranks candidates by combined stock/extended-hours/options activity, and adds the highest-priority names to the scan universe for intraday scalping and swing alerts.

Key controls include:

| Setting | Purpose |
|---|---|
| `USE_AUTO_WATCHLIST` | Enable/disable automatic mover discovery |
| `AUTO_WATCHLIST_LIMIT` | Maximum number of mover symbols to append |
| `MIN_AUTO_VOLUME` | Minimum same-day stock volume for daily-mover qualification |
| `MIN_AUTO_CHANGE_PCT` | Minimum absolute regular-session percentage move |
| `MIN_STOCK_PRICE` | Low-price filter for mover candidates |
| `AUTO_WATCHLIST_USE_EXTENDED_HOURS` | Enable Polygon minute-aggregate pre-market/after-hours scoring |
| `AUTO_WATCHLIST_EXTENDED_CANDIDATE_LIMIT` | Number of top stock candidates to enrich with extended-hours bars |
| `MIN_EXTENDED_HOURS_VOLUME` | Minimum pre-market or after-hours volume for extended-hours qualification |
| `MIN_EXTENDED_HOURS_CHANGE_PCT` | Minimum pre-market or after-hours percentage move versus previous close |
| `AUTO_WATCHLIST_USE_OPTIONS` | Enable Polygon option snapshot volume/OI scoring |
| `AUTO_WATCHLIST_OPTIONS_CANDIDATE_LIMIT` | Number of top stock candidates to enrich with option snapshots |
| `MIN_AUTO_OPTION_VOLUME` | Minimum summed option volume for options-activity qualification |
| `MIN_AUTO_OPTION_OPEN_INTEREST` | Minimum summed option open interest for options-activity qualification |

The configured universe is separated into `CORE_WATCHLIST`, `SECONDARY_WATCHLIST`, and `SPEC_WATCHLIST` so liquid options names stay prioritized while speculative symbols are still available when they become active movers. The expanded `MASTER_WATCHLIST` also documents the broader ETF, sector, AI/semiconductor, crypto beta, biotech, travel, and high-momentum reference universe used when broadening discovery beyond the core tiers.

---

### 🌙 Daily-Only Swing Context Fallback

Swing scanning no longer depends on having intraday minute bars. If minute data is missing, unavailable premarket, or outside the regular session, the bot builds a daily technical context from historical daily bars and can still score swing setups using daily closes, 20/50/200-day moving averages, ATR, relative volume, recent highs/lows, daily trend, weekly trend, and 60-day price history.

This makes after-hours, weekend, and sparse-intraday swing scans more reliable.

---

### 🏆 Swing Benchmark Gate

Swing candidates now pass through a benchmark gate after the AI reasoning report is generated. The benchmark accepts high-quality `A+` or `A` setups with an `88+` composite score, at least `1.8R` risk/reward, aligned trend/regime context or a perfect-score mixed-regime exception, acceptable execution quality, good/strong multi-timeframe structure, `ELITE` or `GOOD` chart structure, and no blocking AI reject risks. Rejected candidates log explicit reasons such as score, risk/reward, regime, execution, MTF, chart-structure, or AI-risk misses.

Outcome tracking now uses the full swing hold window: a displayed range like `2-10 days` is converted to the maximum horizon so the trade has the complete advertised period to reach its stop or target.

---

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

Options support has been expanded with a Polygon snapshot-based selector that can identify liquid near-the-money contracts while requiring high same-day volume and high open interest for every recommendation.

The options layer evaluates:

- Expiration / DTE
- Strike proximity
- Bid / ask / mid
- Spread percentage
- Delta
- Theta
- Implied volatility
- High same-day volume and high open interest
- Volume/OI participation ratio
- OI/volume-weighted recommendation score
- Estimated option dollar volume

The selector now uses the same Polygon/Massive-compatible snapshot client as the options-flow engine. When a directional intraday or swing setup passes, the bot can attach an `Option Pick` that only considers contracts meeting the configured high-volume and high-open-interest floors, then prioritizes the strongest same-day volume, open interest, acceptable spreads, target delta, and nearby strikes instead of simply choosing the closest ATM contract.

The true options flow and liquidity engine can also use Polygon/Massive-compatible options APIs to score explosive intraday and swing conditions:

- Aggressive call / put sweeps and large block-print proxies
- Put and call OI walls
- Fresh OI-build pressure via volume/open-interest ratios
- Dealer gamma state and gamma-squeeze conditions
- IV expansion proxies
- Delta imbalance and call/put premium imbalance

Set `OPTIONS_API_KEY`, `MASSIVE_API_KEY`, or `POLYGON_API_KEY` to enable option recommendations and the flow scan. Optional controls include `OPTIONS_API_BASE_URL`, `MIN_OPTION_VOLUME`, `MIN_OPTION_OI`, `MAX_OPTION_SPREAD_PCT`, `TARGET_MIN_DELTA`, `TARGET_MAX_DELTA`, `OPTIONS_FLOW_EXPIRY_DAYS`, `OPTIONS_SWEEP_NOTIONAL_THRESHOLD`, `OPTIONS_PUT_WALL_OI_THRESHOLD`, `OPTIONS_GAMMA_SQUEEZE_MIN_SCORE`, and `OPTIONS_MAX_SNAPSHOT_AGE_SEC`.

To reduce the practical impact of quote/aggregate drift, intraday stock technicals prefer Polygon's latest entitled stock trade whenever it is fresh and not materially older than the newest minute bar. The Telegram alert also refreshes the displayed price from the latest entitled trade immediately before sending, so the visible alert price is less likely to differ from broker quotes because of scan latency or same-minute aggregate closes. Enable or tune this with `REALTIME_STOCK_OVERLAY_ENABLED`, `REALTIME_STOCK_MAX_AGE_SEC`, `REALTIME_STOCK_AGGREGATE_STALENESS_TOLERANCE_SEC`, `REALTIME_STOCK_OVERLAY_SKIP_UNAUTHORIZED`, and the legacy strict-delay controls `REALTIME_STOCK_OVERLAY_REQUIRE_DELAY` / `REALTIME_STOCK_DELAY_THRESHOLD_SEC`; alerts expose `intraday_data_source`, `latest_price_time`, `intraday_data_delay_sec`, and `realtime_overlay_active` so stale feeds are visible instead of silently affecting scores. Option recommendations also reject snapshots with quote/trade timestamps older than `OPTIONS_MAX_SNAPSHOT_AGE_SEC` while preserving fixtures/providers that do not expose timestamps.

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

The swing engine is a multi-factor confluence system for CALL and PUT swing setups. It supports both full intraday context and a daily-only fallback path for swing scans when minute bars are not available.

## Daily-Only Swing Inputs

When intraday data is unavailable, the scanner can still evaluate swing setups from daily bars using:

- Daily closes and the latest 60 closes
- 20 DMA, 50 DMA, and 200 DMA
- ATR14 for stop/target distance
- Previous-day high/low and recent 20-day high/low
- Current volume, 20-day average volume, and relative volume
- Daily and weekly trend state

## Institutional Swing Price-Action Inputs

The swing scorer also evaluates institutional-style price-action context:

- HH/HL or LH/LL market-structure stages
- 9/21/50 EMA stage alignment
- Pivot/base breakouts and breakdowns
- Volume dry-up during bases
- VCP volatility contraction
- Breakout retest holds and breakdown retest rejections
- Bullish or bearish gap intent with relative-volume confirmation
- ATR extension and late-breakout risk
- Failed reclaim / rejection at key levels

## Swing Quality Benchmark

Before a swing alert is sent, the benchmark layer validates:

- `A+` or `A` reasoning decision
- `88` composite score minimum
- At least `1.8R` risk/reward
- Directional market-regime alignment, with a mixed-regime exception only for perfect-score `A+` setups
- GOOD/WARNING execution quality
- PASS/WARNING/REJECT setup-quality status when other benchmark requirements still pass
- `ELITE` or `GOOD` chart-structure quality
- GOOD/STRONG multi-timeframe alignment
- No blocking AI reject reasons


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

## Telegram Formatting Reliability

Alert messages are HTML-safe by default. The bot escapes dynamic text, preserves simple bold labels, and falls back to plain text when Telegram rejects formatted content. This is designed to keep alerts deliverable even when tickers, setup keys, URLs, or AI explanations contain characters that would otherwise break Markdown parsing.

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
Static Watchlist + Auto Daily Movers
      ↓
Technical Analysis / Daily Swing Context
      ↓
Intraday Engine + Swing Engine
      ↓
Market Regime Detection
      ↓
Multi-Timeframe + Setup Quality Filters
      ↓
AI Reasoning + ML Scoring + Chart Vision
      ↓
Price Projection
      ↓
Probability + Historical Calibration
      ↓
Risk / Execution / Liquid Options Review
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
Market Data APIs + Polygon Daily Movers
        ↓
Technical Analysis Engine / Daily Swing Context
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
AI Reasoning Engine + AI Vision Chart Reader
        ↓
ML Scoring Layers
        ↓
Price Projection Engine
        ↓
Sklearn Probability Model
        ↓
Trade Ranking Engine + Options Contract Selector
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
- Swing benchmark decisions and rejection context through logs
- Options-flow bias, score, and gamma-squeeze fields when available
- Recommended contract, predicted move, and estimated premium-move context when logged
- AI vision chart-structure context when attached to a scan

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
- Neutral performance-learning baselines when history is missing or incomplete

---

# 🔧 Installation

```bash
pip install -r requirements.txt
# Optional: install scikit-learn if you want the logistic regression probability model
pip install scikit-learn
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


## 🧠 OpenAI Market Reasoning Model

StockeAlerts defaults its AI alert gates to `gpt-5-mini` with `medium` reasoning effort so the model can think through trend, volume, regime, risk/reward, entry timing, and options context before approving alerts. Override `OPENAI_REASONING_MODEL` if you need a cheaper or lower-latency model, and adjust `OPENAI_REASONING_EFFORT` (`low`, `medium`, `high`, etc.) to trade speed/cost for deeper reasoning.

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
OPENAI_SCAN_MODEL=gpt-5-mini
OPENAI_HIGH_QUALITY_MODEL=gpt-5.2
OPENAI_HIGH_QUALITY_MIN_SCORE=95
OPENAI_REASONING_MODEL=gpt-5-mini
OPENAI_REASONING_EFFORT=medium
OPENAI_VISION_MODEL=gpt-5-mini
POLYGON_API_KEY=
ENABLE_OUTCOME_TRACKING=true       # Set false to skip post-alert Polygon minute-aggregate outcome checks
OUTCOME_TRACKING_SKIP_UNAUTHORIZED=true  # Disable outcome checks for the run after Polygon plan entitlement errors

# Optional auto-watchlist discovery
AUTO_WATCHLIST_DATE=        # Optional YYYY-MM-DD; uses Polygon historical active movers for that day
AUTO_WATCHLIST_USE_EXTENDED_HOURS=true
AUTO_WATCHLIST_EXTENDED_CANDIDATE_LIMIT=120
MIN_EXTENDED_HOURS_VOLUME=500000
MIN_EXTENDED_HOURS_CHANGE_PCT=2.0
AUTO_WATCHLIST_USE_OPTIONS=true
AUTO_WATCHLIST_OPTIONS_CANDIDATE_LIMIT=80
MIN_AUTO_OPTION_VOLUME=1000
MIN_AUTO_OPTION_OPEN_INTEREST=5000

TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
PAPER_TRADING=true
ENABLE_REAL_EXECUTION=false

# Optional early-session intraday grace
EARLY_SESSION_GRACE_ENABLED=true
EARLY_SESSION_END_TIME=10:30
EARLY_SESSION_MIN_SCORE_BUFFER=10
EARLY_SESSION_MIN_CONFIRMATIONS=2
EARLY_SESSION_REL_VOLUME_MIN=1.0
EXTENDED_HOURS_BIAS_ENABLED=true
EXTENDED_HOURS_BIAS_WEIGHT=12
EXTENDED_HOURS_CONFLICT_PENALTY=10
EXTENDED_HOURS_MIN_MOVE_PCT=0.35
EXTENDED_HOURS_MIN_VOLUME=100000

# Optional ranked alert caps
MAX_INTRADAY_ALERTS_PER_SCAN=5
MAX_SWING_ALERTS_PER_SCAN=5
MAX_HIGH_QUALITY_ALERTS_PER_SCAN=10
MAX_TRADES_PER_TRADING_DAY=10

# Optional options-flow providers and tuning
OPTIONS_API_KEY=
MASSIVE_API_KEY=
OPTIONS_API_BASE_URL=https://api.polygon.io
OPTIONS_FLOW_EXPIRY_DAYS=45
OPTIONS_FLOW_TOP_CONTRACTS=24
OPTIONS_FLOW_TRADE_LIMIT=50
OPTIONS_SWEEP_NOTIONAL_THRESHOLD=250000
OPTIONS_BLOCK_NOTIONAL_THRESHOLD=500000
OPTIONS_PUT_WALL_OI_THRESHOLD=5000
OPTIONS_CALL_WALL_OI_THRESHOLD=5000
OPTIONS_MAX_SNAPSHOT_AGE_SEC=900

# Optional real-time stock last-trade overlay / alert price refresh
REALTIME_STOCK_OVERLAY_ENABLED=true
REALTIME_STOCK_MAX_AGE_SEC=90
REALTIME_STOCK_AGGREGATE_STALENESS_TOLERANCE_SEC=60
REALTIME_STOCK_OVERLAY_REQUIRE_DELAY=false
REALTIME_STOCK_OVERLAY_SKIP_UNAUTHORIZED=true
REALTIME_STOCK_DELAY_THRESHOLD_SEC=180
OPTIONS_OI_BUILD_VOLUME_OI_RATIO=0.35
OPTIONS_IV_EXPANSION_RATIO=1.15
OPTIONS_DELTA_IMBALANCE_RATIO=1.75
OPTIONS_GAMMA_SQUEEZE_MIN_SCORE=70

# Optional contract-selection tuning
MIN_OPTION_VOLUME=1000
MIN_OPTION_OI=5000
MAX_OPTION_SPREAD_PCT=12
MAX_OPTION_IV=1.20
TARGET_MIN_DELTA=0.35
TARGET_MAX_DELTA=0.65
MIN_OPTION_PREMIUM=0.50
MIN_OPTION_DTE=7
MAX_OPTION_DTE=45
HIGH_VOLUME_OPTION_MIN_VOLUME=10000
HIGH_VOLUME_OPTION_MIN_DTE=0

# Optional paper options auto-trading
ENABLE_AUTO_OPTION_TRADING=true
AUTO_OPTION_PAPER_ONLY=true
OPTION_CONTRACT_QTY=1
MIN_OPTION_BUY_PREMIUM=0.50
OPTION_PROFIT_TARGET_PCT=50
OPTION_STOP_LOSS_PCT=-50
OPTION_PRICE_CHECK_INTERVAL_SEC=300
OPTION_ORDER_STATE_FILE=option_order_state.json
```

---

# 🚀 Next Planned Upgrades

## 📈 Portfolio & Position Management

- Expanded open-position tracking
- Portfolio exposure management
- Risk balancing
- Sector concentration limits

## 💵 Live PnL Dashboard

- Real-time PnL
- Trade analytics
- Win rate by setup
- Daily/weekly performance

## 🤖 Auto Trading (Alpaca)

- Expanded automated execution controls
- Smart order routing
- Dynamic position sizing
- Stop/target automation


### Paper Options Auto-Trading

Recommended option contracts included in intraday and swing alerts can be submitted to Alpaca as paper limit orders. The bot records submitted orders, resolves the actual broker fill price when available, refreshes the latest option premium every five minutes by default, and submits a paper sell when the premium reaches the configured profit target or stop loss measured from the filled entry.

Environment controls:

- `PAPER_TRADING=true` keeps Alpaca in paper mode.
- `AUTO_OPTION_PAPER_ONLY=true` blocks option automation if Alpaca is not in paper mode.
- `ENABLE_AUTO_OPTION_TRADING=true` enables automated option buys from recommended contracts.
- `OPTION_CONTRACT_QTY=1` sets the number of contracts per alert.
- `MIN_OPTION_BUY_PREMIUM=0.50` skips low-premium option orders before submission.
- `MAX_TRADES_PER_TRADING_DAY=10` stops additional paper buys after the daily market-local trade cap is reached.
- `OPTION_PROFIT_TARGET_PCT=50` submits the managed sell at +50% option P/L from the actual filled premium.
- `OPTION_STOP_LOSS_PCT=-50` submits the managed sell at -50% option P/L from the actual filled premium.
- `OPTION_PRICE_CHECK_INTERVAL_SEC=300` checks submitted option order prices every five minutes by default.
- `OPTION_ORDER_STATE_FILE=option_order_state.json` stores tracked paper option positions, pending fills, broker fill metadata, and daily trade counts between scans.

Telegram confirmations are sent for each paper buy submission, pending-fill resolution, paper sell submission, and any guardrail skip such as non-paper Alpaca mode, low premium, duplicate tracked contracts, or daily cap exhaustion.

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
- Early-session intraday grace applies only during the configured morning window and still depends on final score, AI, confirmation, and risk/reward checks.
- Alpaca option automation is designed for paper trading first; live execution remains blocked unless explicitly enabled with `ENABLE_REAL_EXECUTION=true`.
- Swing analysis can run after hours and can fall back to daily-only context.
- Auto watchlist discovery uses Polygon live snapshots by default; set `AUTO_WATCHLIST_DATE=YYYY-MM-DD` to build the active mover watchlist for a specific historical trading day from Polygon reference tickers plus grouped daily aggregates.
- Options-flow scoring depends on provider snapshot fields and should be treated as a proxy, not a complete tape feed.
- Price projections and estimated option premium moves are probabilistic estimates, not guarantees.
- AI vision requires TradingView pages to load successfully in the local browser environment.
- Not financial advice.

---

# 👨‍💻 Author

Bhanu Yamzala
