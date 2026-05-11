import datetime as dt
from config import *
from polygon import RESTClient
from performance_learning import refresh_learning_model
from outcome_schema import append_outcome_row

client = RESTClient(POLYGON_API_KEY)

OUTCOME_FILE = "alert_outcomes.csv"


def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def _move_pct(direction, entry, target):
    if not entry or not target:
        return 0.0
    if direction == "CALL":
        return ((target - entry) / entry) * 100
    return ((entry - target) / entry) * 100


def _forecast_accuracy(expected_move_pct, realized_move_pct):
    expected = abs(safe_float(expected_move_pct))
    if expected <= 0:
        return 0.0
    error = abs(expected - abs(safe_float(realized_move_pct)))
    return round(max(0.0, min(100.0, (1 - (error / expected)) * 100)), 2)


def track_outcome(
    ticker,
    direction,
    entry,
    stop,
    target,
    alert_time_iso,
    *,
    alert_type="INTRADAY",
    entry_mode="STANDARD",
    setup_context=None,
    horizon_minutes=60,
):
    alert_time = dt.datetime.fromisoformat(alert_time_iso)
    end_time = alert_time + dt.timedelta(minutes=horizon_minutes)
    setup_context = setup_context or {}

    try:
        bars = list(
            client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="minute",
                from_=alert_time.date().isoformat(),
                to=end_time.date().isoformat(),
                adjusted=True,
                sort="asc",
                limit=50000,
            )
        )
    except Exception as e:
        print(f"{ticker}: outcome fetch error {e}")
        return None

    target_hit = False
    stop_hit = False
    target_time = None
    stop_time = None

    max_gain = 0.0
    max_loss = 0.0

    for bar in bars:
        bar_time = dt.datetime.fromtimestamp(
            bar.timestamp / 1000,
            tz=dt.timezone.utc
        )

        if bar_time < alert_time or bar_time > end_time:
            continue

        high = safe_float(bar.high)
        low = safe_float(bar.low)

        if direction == "CALL":
            gain = ((high - entry) / entry) * 100
            loss = ((entry - low) / entry) * 100

            if high >= target and not target_hit:
                target_hit = True
                target_time = bar_time.isoformat()

            if low <= stop and not stop_hit:
                stop_hit = True
                stop_time = bar_time.isoformat()

        else:
            gain = ((entry - low) / entry) * 100
            loss = ((high - entry) / entry) * 100

            if low <= target and not target_hit:
                target_hit = True
                target_time = bar_time.isoformat()

            if high >= stop and not stop_hit:
                stop_hit = True
                stop_time = bar_time.isoformat()

        max_gain = max(max_gain, gain)
        max_loss = max(max_loss, loss)

        if target_hit or stop_hit:
            break

    if target_hit and not stop_hit:
        result = "WIN"
    elif stop_hit and not target_hit:
        result = "LOSS"
    elif target_hit and stop_hit:
        result = "MIXED"
    else:
        result = "OPEN_OR_BREAKEVEN"

    row = {
        "timestamp": alert_time_iso,
        "ticker": ticker,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "alert_type": alert_type,
        "entry_mode": entry_mode,
        "setup_key": setup_context.get("setup_key"),
        "market_regime": setup_context.get("market_regime"),
        "mtf_structure": setup_context.get("mtf_structure"),
        "chart_structure": setup_context.get("chart_structure"),
        "ai_confidence": setup_context.get("ai_confidence"),
        "calibrated_confidence": setup_context.get("calibrated_confidence"),
        "score": setup_context.get("score"),
        "expected_move_pct": round(_move_pct(direction, entry, target), 2),
        "result": result,
        "target_hit": target_hit,
        "stop_hit": stop_hit,
        "target_time": target_time,
        "stop_time": stop_time,
        "max_gain_pct": round(max_gain, 2),
        "max_loss_pct": round(max_loss, 2),
    }
    row["forecast_accuracy_pct"] = _forecast_accuracy(row["expected_move_pct"], row["max_gain_pct"])

    append_outcome_row(OUTCOME_FILE, row)

    try:
        refresh_learning_model()
    except Exception as e:
        print(f"{ticker}: learning refresh skipped {e}")

    return row
