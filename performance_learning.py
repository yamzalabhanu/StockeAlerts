import datetime as dt
import json
import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from config import LOG_FILE
from outcome_schema import read_outcome_rows

OUTCOME_FILE = "alert_outcomes.csv"
LEARNING_FILE = "setup_performance_learning.json"
MIN_SAMPLES_FOR_CONFIDENCE = 3
DEFAULT_WIN_RATE = 0.50
DEFAULT_FORECAST_ACCURACY = 0.50
MAX_CONFIDENCE_ADJUSTMENT = 15
MAX_SCORE_ADJUSTMENT = 12
MIN_SIMILAR_CONTEXT_SAMPLES = 4
MAX_CONTEXT_MEMORY_ADJUSTMENT = 10


def default_learning_stats() -> Dict[str, Any]:
    """Neutral learning values used until enough closed alerts exist.

    A missing history bucket should never display as a 0% win rate/forecast;
    0% is only accurate when historical data actually proves it.
    """
    return {
        "wins": 0,
        "losses": 0,
        "open": 0,
        "total": 0,
        "closed": 0,
        "win_rate": DEFAULT_WIN_RATE,
        "forecast_accuracy": DEFAULT_FORECAST_ACCURACY,
        "forecast_accuracy_samples": 0,
        "avg_max_gain_pct": 0.0,
        "avg_max_loss_pct": 0.0,
        "confidence_adjustment": 0.0,
        "score_adjustment": 0.0,
        "learning_status": "BASELINE",
    }


def _complete_learning_stats(stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    completed = default_learning_stats()
    completed.update(stats or {})
    completed["closed"] = _safe_int(
        completed.get("closed"),
        _safe_int(completed.get("wins")) + _safe_int(completed.get("losses")),
    )
    completed["win_rate"] = _safe_float(completed.get("win_rate"), DEFAULT_WIN_RATE)
    completed["forecast_accuracy"] = _safe_float(completed.get("forecast_accuracy"), DEFAULT_FORECAST_ACCURACY)
    completed["forecast_accuracy_samples"] = _safe_int(completed.get("forecast_accuracy_samples"))
    if completed["closed"] >= MIN_SAMPLES_FOR_CONFIDENCE:
        completed.setdefault("learning_status", "HISTORICAL")
        if completed.get("learning_status") == "BASELINE":
            completed["learning_status"] = "HISTORICAL"
    return completed


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _normalize(value: Any, default: str = "UNKNOWN") -> str:
    text = str(value or "").strip().upper()
    return text or default


def _read_csv_rows(path: str) -> List[Dict[str, Any]]:
    return read_outcome_rows(path)


def _is_win(row: Dict[str, Any]) -> Optional[bool]:
    result = _normalize(row.get("result", row.get("outcome", "")), "")
    if result in {"WIN", "TARGET", "TP", "TP1", "TP2", "PROFIT", "TRUE", "1"}:
        return True
    if result in {"LOSS", "STOP", "SL", "FAILED", "FALSE", "0"}:
        return False
    if result == "MIXED":
        return _safe_float(row.get("max_gain_pct")) >= _safe_float(row.get("max_loss_pct"))
    return None


def setup_structure_key(row: Dict[str, Any]) -> str:
    """Stable structure key used for setup-level learning and ranking."""
    alert_type = _normalize(row.get("alert_type"), "INTRADAY")
    entry_mode = _normalize(row.get("entry_mode"), "STANDARD")
    direction = _normalize(row.get("direction"), "ANY")
    mtf = _normalize(row.get("mtf_structure"), "ANY")
    chart = _normalize(row.get("chart_structure"), "ANY")
    regime = _normalize(row.get("market_regime"), "ANY")
    return f"{alert_type}:{entry_mode}:{direction}:{mtf}:{chart}:{regime}"


def _context_value(row: Dict[str, Any], *keys: str, default: str = "ANY") -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get("phase") or value.get("structure") or value.get("quality")
        normalized = _normalize(value, "")
        if normalized:
            return normalized
    return default


def enriched_context_key(row: Dict[str, Any]) -> str:
    """Stable key for Phase 4 similar-context outcome memory.

    This is intentionally broader than ticker-level learning.  It groups trades
    by the dimensions now captured in the enriched outcome schema so the bot can
    learn that, for example, a breakout call in an exhaustion phase with weak
    option liquidity behaves differently from the same setup in an open drive.
    """
    alert_type = _normalize(row.get("alert_type"), "INTRADAY")
    entry_mode = _normalize(row.get("entry_mode"), "STANDARD")
    direction = _normalize(row.get("direction"), "ANY")
    phase = _context_value(row, "market_phase", default="ANY")
    session = _context_value(row, "session_time_bucket", "session_bucket", default="ANY")
    mtf = _context_value(row, "mtf_structure", default="ANY")
    chart = _context_value(row, "chart_structure", "vision_quality", default="ANY")
    option_liquidity = _option_liquidity_bucket(row)
    return f"CTX:{alert_type}:{entry_mode}:{direction}:{phase}:{session}:{mtf}:{chart}:{option_liquidity}"


def _option_liquidity_bucket(row: Dict[str, Any]) -> str:
    spread = _safe_float(row.get("option_spread_pct"), None)
    volume = _safe_float(row.get("option_volume"), None)
    open_interest = _safe_float(row.get("option_open_interest"), None)
    if spread is None and volume is None and open_interest is None:
        return "ANY"
    if spread is not None and spread > 25:
        return "WIDE_SPREAD"
    if (volume is not None and volume >= 1000) or (open_interest is not None and open_interest >= 2000):
        return "DEEP_LIQUIDITY"
    if (volume is not None and volume >= 200) or (open_interest is not None and open_interest >= 500):
        return "NORMAL_LIQUIDITY"
    return "THIN_LIQUIDITY"


def _context_group_keys(row: Dict[str, Any]) -> Iterable[str]:
    alert_type = _normalize(row.get("alert_type"), "INTRADAY")
    entry_mode = _normalize(row.get("entry_mode"), "STANDARD")
    direction = _normalize(row.get("direction"), "ANY")
    phase = _context_value(row, "market_phase", default="ANY")
    session = _context_value(row, "session_time_bucket", "session_bucket", default="ANY")
    mtf = _context_value(row, "mtf_structure", default="ANY")
    chart = _context_value(row, "chart_structure", "vision_quality", default="ANY")
    liquidity = _option_liquidity_bucket(row)
    yield f"CTX_MODE:{entry_mode}:{direction}:{phase}"
    yield f"CTX_SESSION:{entry_mode}:{direction}:{phase}:{session}"
    yield f"CTX_STRUCTURE:{entry_mode}:{direction}:{phase}:{mtf}:{chart}"
    yield f"CTX_LIQUIDITY:{alert_type}:{entry_mode}:{direction}:{phase}:{liquidity}"
    yield enriched_context_key(row)


def _group_keys(row: Dict[str, Any]) -> Iterable[str]:
    alert_type = _normalize(row.get("alert_type"), "INTRADAY")
    entry_mode = _normalize(row.get("entry_mode"), "STANDARD")
    direction = _normalize(row.get("direction"), "ANY")
    yield "ALL"
    yield f"TYPE:{alert_type}"
    yield f"MODE:{entry_mode}"
    yield f"MODE_DIR:{entry_mode}:{direction}"
    yield f"STRUCTURE:{setup_structure_key(row)}"
    yield from _context_group_keys(row)


def _forecast_accuracy(row: Dict[str, Any]) -> Optional[float]:
    win = _is_win(row)
    if win is None:
        return None

    max_gain = _safe_float(row.get("max_gain_pct"))

    explicit = row.get("forecast_accuracy_pct")
    if explicit not in (None, ""):
        return max(0.0, min(1.0, _safe_float(explicit) / 100.0))

    expected = abs(_safe_float(row.get("expected_move_pct")))
    if expected <= 0:
        entry = _safe_float(row.get("entry"))
        target = _safe_float(row.get("target"))
        if entry and target:
            expected = abs((target - entry) / entry) * 100.0

    if expected <= 0:
        return None

    realized = abs(max_gain)
    error = abs(expected - realized)
    return max(0.0, min(1.0, 1.0 - (error / expected)))


def load_learning(path: str = LEARNING_FILE) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_learning(model: Dict[str, Any], path: str = LEARNING_FILE) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2, sort_keys=True)

    from learning_replay_scheduler import maybe_run_after_learning_change

    maybe_run_after_learning_change(model_files=[path])


def build_learning_model(rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = rows if rows is not None else _read_csv_rows(OUTCOME_FILE)
    buckets: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "wins": 0,
            "losses": 0,
            "open": 0,
            "total": 0,
            "forecast_accuracy_sum": 0.0,
            "forecast_accuracy_samples": 0,
            "avg_max_gain_pct_sum": 0.0,
            "avg_max_loss_pct_sum": 0.0,
        }
    )

    for row in rows:
        for key in _group_keys(row):
            bucket = buckets[key]
            bucket["total"] += 1
            win = _is_win(row)
            if win is True:
                bucket["wins"] += 1
            elif win is False:
                bucket["losses"] += 1
            else:
                bucket["open"] += 1

            accuracy = _forecast_accuracy(row)
            if accuracy is not None:
                bucket["forecast_accuracy_sum"] += accuracy
                bucket["forecast_accuracy_samples"] += 1

            bucket["avg_max_gain_pct_sum"] += _safe_float(row.get("max_gain_pct"))
            bucket["avg_max_loss_pct_sum"] += _safe_float(row.get("max_loss_pct"))

    model = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "buckets": {},
    }

    for key, bucket in buckets.items():
        closed = bucket["wins"] + bucket["losses"]
        total = max(bucket["total"], 1)
        win_rate = (bucket["wins"] / closed) if closed else DEFAULT_WIN_RATE
        forecast_samples = bucket["forecast_accuracy_samples"]
        forecast_accuracy = (
            bucket["forecast_accuracy_sum"] / forecast_samples
            if forecast_samples else DEFAULT_FORECAST_ACCURACY
        )
        sample_factor = min(1.0, closed / 20.0)
        edge = ((win_rate - DEFAULT_WIN_RATE) * 0.70) + ((forecast_accuracy - DEFAULT_FORECAST_ACCURACY) * 0.30)
        confidence_adjustment = round(
            max(-MAX_CONFIDENCE_ADJUSTMENT, min(MAX_CONFIDENCE_ADJUSTMENT, edge * 100.0 * sample_factor)),
            2,
        )
        score_adjustment = round(
            max(-MAX_SCORE_ADJUSTMENT, min(MAX_SCORE_ADJUSTMENT, confidence_adjustment * 0.8)),
            2,
        )

        model["buckets"][key] = {
            "wins": bucket["wins"],
            "losses": bucket["losses"],
            "open": bucket["open"],
            "total": bucket["total"],
            "closed": closed,
            "win_rate": round(win_rate, 4),
            "forecast_accuracy": round(forecast_accuracy, 4),
            "forecast_accuracy_samples": forecast_samples,
            "avg_max_gain_pct": round(bucket["avg_max_gain_pct_sum"] / total, 2),
            "avg_max_loss_pct": round(bucket["avg_max_loss_pct_sum"] / total, 2),
            "confidence_adjustment": confidence_adjustment if closed >= MIN_SAMPLES_FOR_CONFIDENCE else 0.0,
            "score_adjustment": score_adjustment if closed >= MIN_SAMPLES_FOR_CONFIDENCE else 0.0,
        }

    return model


def refresh_learning_model(rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    model = build_learning_model(rows)
    save_learning(model)
    return model


def get_bucket_stats(key: str, model: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    model = model or load_learning()
    return (model.get("buckets") or {}).get(key, {})


def get_setup_learning(row: Dict[str, Any], model: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    model = model or load_learning()
    keys = list(_group_keys(row))
    buckets = model.get("buckets") or {}
    best = None
    best_key = None

    for key in reversed(keys):
        stats = buckets.get(key) or {}
        if _safe_int(stats.get("closed")) >= MIN_SAMPLES_FOR_CONFIDENCE:
            best = stats
            best_key = key
            break

    if best is None:
        # Prefer the broad aggregate bucket over an empty structure bucket. This
        # keeps WR/Forecast representative of observed history when a specific
        # setup has too few samples.
        fallback_keys = (
            "ALL",
            f"MODE_DIR:{_normalize(row.get('entry_mode'), 'STANDARD')}:{_normalize(row.get('direction'), 'ANY')}",
            keys[-1],
        )
        for key in fallback_keys:
            stats = buckets.get(key) or {}
            if stats:
                best = stats
                best_key = key
                break

    if best is None:
        best = default_learning_stats()
        best_key = "BASELINE"

    return {"key": best_key, "stats": _complete_learning_stats(best)}


def calibrate_confidence(base_confidence: Any, setup_context: Dict[str, Any]) -> Dict[str, Any]:
    base = _safe_float(base_confidence)
    learning = get_setup_learning(setup_context)
    stats = learning.get("stats") or {}
    adjustment = _safe_float(stats.get("confidence_adjustment"))
    calibrated = round(max(0.0, min(100.0, base + adjustment)), 2)
    return {
        "base_confidence": base,
        "calibrated_confidence": calibrated,
        "confidence_adjustment": adjustment,
        "learning_key": learning.get("key"),
        "learning_stats": stats,
    }


def score_adjustment(setup_context: Dict[str, Any]) -> float:
    learning = get_setup_learning(setup_context)
    return _safe_float((learning.get("stats") or {}).get("score_adjustment"))


def similar_context_memory(row: Dict[str, Any], model: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return Phase 4 historical stats for the closest enriched context bucket."""
    model = model or load_learning()
    buckets = model.get("buckets") or {}
    best_key = None
    best_stats: Dict[str, Any] | None = None
    for key in reversed(list(_context_group_keys(row))):
        stats = buckets.get(key) or {}
        if _safe_int(stats.get("closed")) >= MIN_SIMILAR_CONTEXT_SAMPLES:
            best_key = key
            best_stats = stats
            break
    if best_stats is None:
        return {
            "key": enriched_context_key(row),
            "status": "BASELINE",
            "closed": 0,
            "win_rate": DEFAULT_WIN_RATE,
            "forecast_accuracy": DEFAULT_FORECAST_ACCURACY,
            "score_adjustment": 0.0,
            "confidence_adjustment": 0.0,
            "reason": "Not enough matching enriched-context outcomes yet",
        }

    completed = _complete_learning_stats(best_stats)
    edge = (completed["win_rate"] - DEFAULT_WIN_RATE) * 0.75 + (completed["forecast_accuracy"] - DEFAULT_FORECAST_ACCURACY) * 0.25
    sample_factor = min(1.0, completed["closed"] / 20.0)
    adjustment = round(max(-MAX_CONTEXT_MEMORY_ADJUSTMENT, min(MAX_CONTEXT_MEMORY_ADJUSTMENT, edge * 100.0 * sample_factor)), 2)
    return {
        "key": best_key,
        "status": "HISTORICAL",
        "closed": completed["closed"],
        "win_rate": completed["win_rate"],
        "forecast_accuracy": completed["forecast_accuracy"],
        "avg_max_gain_pct": completed.get("avg_max_gain_pct", 0.0),
        "avg_max_loss_pct": completed.get("avg_max_loss_pct", 0.0),
        "score_adjustment": adjustment,
        "confidence_adjustment": round(adjustment * 0.8, 2),
        "reason": f"Similar context {best_key} won {completed['win_rate'] * 100:.1f}% over {completed['closed']} closed alerts",
    }


def priority_bonus(setup_context: Dict[str, Any]) -> float:
    learning = get_setup_learning(setup_context)
    stats = learning.get("stats") or {}
    closed = _safe_int(stats.get("closed"))
    if closed < MIN_SAMPLES_FOR_CONFIDENCE:
        return 0.0
    win_rate = _safe_float(stats.get("win_rate"), DEFAULT_WIN_RATE)
    forecast_accuracy = _safe_float(stats.get("forecast_accuracy"), DEFAULT_FORECAST_ACCURACY)
    bonus = ((win_rate - DEFAULT_WIN_RATE) * 25.0) + ((forecast_accuracy - DEFAULT_FORECAST_ACCURACY) * 10.0)
    return round(max(-15.0, min(20.0, bonus)), 2)


def strongest_setups(limit: int = 5) -> List[Dict[str, Any]]:
    model = load_learning()
    buckets = model.get("buckets") or {}
    structures = [
        {"key": key, **stats}
        for key, stats in buckets.items()
        if key.startswith("STRUCTURE:") and stats.get("closed", 0) >= MIN_SAMPLES_FOR_CONFIDENCE
    ]
    return sorted(
        structures,
        key=lambda item: (item.get("win_rate", 0), item.get("forecast_accuracy", 0), item.get("closed", 0)),
        reverse=True,
    )[:limit]
