import csv
import datetime as dt
import json
import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from config import LOG_FILE

OUTCOME_FILE = "alert_outcomes.csv"
LEARNING_FILE = "setup_performance_learning.json"
MIN_SAMPLES_FOR_CONFIDENCE = 3
DEFAULT_WIN_RATE = 0.50
DEFAULT_FORECAST_ACCURACY = 0.50
MAX_CONFIDENCE_ADJUSTMENT = 15
MAX_SCORE_ADJUSTMENT = 12


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
    if not os.path.exists(path):
        return []

    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


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


def _group_keys(row: Dict[str, Any]) -> Iterable[str]:
    alert_type = _normalize(row.get("alert_type"), "INTRADAY")
    entry_mode = _normalize(row.get("entry_mode"), "STANDARD")
    direction = _normalize(row.get("direction"), "ANY")
    yield "ALL"
    yield f"TYPE:{alert_type}"
    yield f"MODE:{entry_mode}"
    yield f"MODE_DIR:{entry_mode}:{direction}"
    yield f"STRUCTURE:{setup_structure_key(row)}"


def _forecast_accuracy(row: Dict[str, Any]) -> Optional[float]:
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

    realized = abs(_safe_float(row.get("max_gain_pct")))
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
    best = {}
    best_key = None
    for key in reversed(keys):
        stats = buckets.get(key) or {}
        if stats.get("closed", 0) >= MIN_SAMPLES_FOR_CONFIDENCE:
            best = stats
            best_key = key
            break
    if not best:
        best_key = keys[-1]
        best = buckets.get(best_key) or {}
    return {"key": best_key, "stats": best}


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
