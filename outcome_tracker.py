import datetime as dt
from config import *
from polygon import RESTClient
from performance_learning import refresh_learning_model
from outcome_schema import append_outcome_row

client = RESTClient(POLYGON_API_KEY)

OUTCOME_FILE = "alert_outcomes.csv"

_outcome_tracking_disabled_reason = None


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


def _is_polygon_not_authorized_error(error):
    """Return True when Polygon rejects the requested data entitlement."""
    text = str(error).lower()
    return "not_authorized" in text or "doesn't include this data timeframe" in text


def _disable_outcome_tracking(reason):
    """Disable outcome tracking for this process after a plan entitlement failure."""
    global _outcome_tracking_disabled_reason
    if not _outcome_tracking_disabled_reason:
        _outcome_tracking_disabled_reason = reason
        print(f"Outcome tracking disabled for this run: {reason}")


def _outcome_tracking_enabled():
    return globals().get("ENABLE_OUTCOME_TRACKING", True)


def _skip_unauthorized_outcomes():
    return globals().get("OUTCOME_TRACKING_SKIP_UNAUTHORIZED", True)



def _nested_get(mapping, *keys):
    current = mapping
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current in (None, ""):
            return None
    return current


def _first_context_value(context, *paths):
    for path in paths:
        if isinstance(path, str):
            value = context.get(path) if isinstance(context, dict) else None
        else:
            value = _nested_get(context, *path)
        if value not in (None, ""):
            return value
    return None


def _time_of_day_bucket(alert_time):
    try:
        local_time = alert_time.astimezone(MARKET_TZ).time()
    except Exception:
        local_time = alert_time.time()

    if local_time < dt.time(9, 30):
        return "PREMARKET"
    if local_time < dt.time(10, 0):
        return "OPENING_30"
    if local_time < dt.time(11, 30):
        return "MORNING"
    if local_time < dt.time(13, 30):
        return "MIDDAY"
    if local_time < dt.time(15, 0):
        return "AFTERNOON"
    if local_time < dt.time(16, 0):
        return "POWER_HOUR"
    return "AFTER_HOURS"


def _enriched_context_fields(setup_context, alert_time):
    context = setup_context or {}
    return {
        "market_phase": _first_context_value(
            context, "market_phase", ("reasoning", "market_phase", "phase")
        ),
        "time_of_day_bucket": _time_of_day_bucket(alert_time),
        "atr_extension": _first_context_value(
            context,
            "atr_extension",
            "breakout_distance_atr",
            ("tech", "atr_extension"),
            ("tech", "breakout_distance_atr"),
            ("setup", "atr_extension"),
            ("setup", "breakout_distance_atr"),
        ),
        "wick_ratio": _first_context_value(
            context, "wick_ratio", ("tech", "wick_ratio"), ("setup", "wick_ratio")
        ),
        "candle_body_pct": _first_context_value(
            context,
            "candle_body_pct",
            "body_pct",
            ("tech", "candle_body_pct"),
            ("tech", "body_pct"),
            ("setup", "candle_body_pct"),
            ("setup", "body_pct"),
        ),
        "distance_from_vwap": _first_context_value(
            context,
            "distance_from_vwap",
            ("tech", "distance_from_vwap"),
            ("setup", "distance_from_vwap"),
        ),
        "distance_from_ema21": _first_context_value(
            context,
            "distance_from_ema21",
            "price_vs_ema21_pct",
            ("tech", "distance_from_ema21"),
            ("tech", "price_vs_ema21_pct"),
            ("setup", "distance_from_ema21"),
        ),
        "rel_volume": _first_context_value(
            context,
            "rel_volume",
            "relative_volume",
            ("tech", "rel_volume"),
            ("tech", "relative_volume"),
            ("setup", "rel_volume"),
        ),
        "spread_pct": _first_context_value(
            context, "spread_pct", ("option_contract", "spread_pct"), ("tech", "spread_pct")
        ),
        "option_volume": _first_context_value(
            context, "option_volume", ("option_contract", "volume"), ("option_contract", "option_volume")
        ),
        "open_interest": _first_context_value(
            context, "open_interest", ("option_contract", "open_interest")
        ),
        "option_contract_symbol": _first_context_value(
            context, "option_contract_symbol", ("option_contract", "contract_symbol")
        ),
        "option_entry_price": _first_context_value(
            context, "option_entry_price", ("option_contract", "ask"), ("option_contract", "mid"), ("option_contract", "bid")
        ),
        "sector_relative_strength": _first_context_value(
            context,
            "sector_relative_strength",
            ("tech", "sector_relative_strength"),
            ("setup", "sector_relative_strength"),
        ),
        "deep_ai_approval": _first_context_value(
            context, "deep_ai_approval", ("ai", "verdict"), ("ai", "decision")
        ),
        "deep_ai_rejection_reason": _first_context_value(
            context, "deep_ai_rejection_reason", ("ai", "reason"), ("reasoning", "reject_reasons")
        ),
    }


def _option_entry_price(option_contract):
    if not isinstance(option_contract, dict):
        return 0.0
    for key in ("ask", "mid", "mark", "last", "bid"):
        value = safe_float(option_contract.get(key), 0.0)
        if value > 0:
            return value
    return 0.0


def _bar_price(bar, attr, default=0.0):
    return safe_float(getattr(bar, attr, default), default)


def _option_outcome_fields(setup_context, alert_time, end_time):
    option_contract = (setup_context or {}).get("option_contract") or {}
    if not isinstance(option_contract, dict):
        return {}
    contract_symbol = option_contract.get("contract_symbol")
    entry = _option_entry_price(option_contract)
    if not contract_symbol or entry <= 0:
        return {}

    target_price = entry * (1 + (OPTION_OUTCOME_TARGET_PCT / 100.0))
    stop_price = entry * max(0.01, 1 - (OPTION_OUTCOME_STOP_PCT / 100.0))
    target_hit = False
    stop_hit = False
    max_gain = 0.0
    max_loss = 0.0

    try:
        option_bars = list(
            client.list_aggs(
                ticker=contract_symbol,
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
        if not (_skip_unauthorized_outcomes() and _is_polygon_not_authorized_error(e)):
            print(f"{contract_symbol}: option outcome fetch error {e}")
        return {
            "option_contract_symbol": contract_symbol,
            "option_entry_price": round(entry, 2),
            "option_target_price": round(target_price, 2),
            "option_stop_price": round(stop_price, 2),
        }

    for bar in option_bars:
        bar_time = dt.datetime.fromtimestamp(bar.timestamp / 1000, tz=dt.timezone.utc)
        if bar_time < alert_time or bar_time > end_time:
            continue
        high = _bar_price(bar, "high")
        low = _bar_price(bar, "low")
        if high >= target_price:
            target_hit = True
        if low <= stop_price:
            stop_hit = True
        max_gain = max(max_gain, ((high - entry) / entry) * 100)
        max_loss = max(max_loss, ((entry - low) / entry) * 100)
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

    return {
        "option_contract_symbol": contract_symbol,
        "option_entry_price": round(entry, 2),
        "option_target_price": round(target_price, 2),
        "option_stop_price": round(stop_price, 2),
        "option_target_hit": target_hit,
        "option_stop_hit": stop_hit,
        "option_result": result,
        "option_max_gain_pct": round(max_gain, 2),
        "option_max_loss_pct": round(max_loss, 2),
    }


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
    if not _outcome_tracking_enabled():
        return None

    if _outcome_tracking_disabled_reason:
        return None

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
        if _skip_unauthorized_outcomes() and _is_polygon_not_authorized_error(e):
            _disable_outcome_tracking(
                "Polygon API plan does not include the requested minute aggregate timeframe. "
                "Set ENABLE_OUTCOME_TRACKING=false to skip outcome checks permanently or upgrade Polygon access."
            )
        else:
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
        "ml_probability": setup_context.get("ml_probability"),
        "win_probability": setup_context.get("win_probability"),
        "expected_move_pct": round(_move_pct(direction, entry, target), 2),
        "result": result,
        "target_hit": target_hit,
        "stop_hit": stop_hit,
        "target_time": target_time,
        "stop_time": stop_time,
        "max_gain_pct": round(max_gain, 2),
        "max_loss_pct": round(max_loss, 2),
    }
    row.update(_enriched_context_fields(setup_context, alert_time))
    row.update(_option_outcome_fields(setup_context, alert_time, end_time))
    row["forecast_accuracy_pct"] = _forecast_accuracy(row["expected_move_pct"], row["max_gain_pct"])

    append_outcome_row(OUTCOME_FILE, row)

    try:
        refresh_learning_model()
    except Exception as e:
        print(f"{ticker}: learning refresh skipped {e}")

    return row
