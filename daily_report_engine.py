import datetime as dt
from typing import Any, Dict, List

from outcome_schema import read_outcome_rows
from performance_learning import OUTCOME_FILE, refresh_learning_model, strongest_setups


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "0.0%"


def _bucket_line(label: str, stats: Dict[str, Any]) -> str:
    return (
        f"{label}: WR {_pct(stats.get('win_rate', 0))} "
        f"({stats.get('wins', 0)}W/{stats.get('losses', 0)}L), "
        f"forecast {_pct(stats.get('forecast_accuracy', 0))}, "
        f"conf adj {stats.get('confidence_adjustment', 0):+.1f}, "
        f"score adj {stats.get('score_adjustment', 0):+.1f}"
    )


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _is_win(row: Dict[str, Any]) -> bool | None:
    result = str(row.get("option_result") or row.get("result") or "").upper()
    if result == "WIN":
        return True
    if result == "LOSS":
        return False
    return None


def probability_calibration_summary(path: str = OUTCOME_FILE) -> Dict[str, Any]:
    """Compare predicted/calibrated probabilities with realized closed outcomes."""
    buckets = [
        (0.0, 0.6, "<60%"),
        (0.6, 0.7, "60-70%"),
        (0.7, 0.8, "70-80%"),
        (0.8, 0.9, "80-90%"),
        (0.9, 1.01, "90%+"),
    ]
    rows = read_outcome_rows(path)
    bucket_stats = {
        label: {"label": label, "samples": 0, "wins": 0, "losses": 0, "predicted_sum": 0.0}
        for _, _, label in buckets
    }
    total_abs_error = 0.0
    samples = 0

    for row in rows:
        win = _is_win(row)
        if win is None:
            continue
        probability = _safe_float(row.get("win_probability"), None)
        if probability is None:
            probability = _safe_float(row.get("ml_probability"), None)
        if probability is None:
            confidence = _safe_float(row.get("calibrated_confidence"), None)
            probability = confidence / 100.0 if confidence is not None and confidence > 1 else confidence
        if probability is None:
            continue
        probability = max(0.0, min(1.0, probability))
        for low, high, label in buckets:
            if low <= probability < high:
                stats = bucket_stats[label]
                stats["samples"] += 1
                stats["wins"] += 1 if win else 0
                stats["losses"] += 0 if win else 1
                stats["predicted_sum"] += probability
                break
        total_abs_error += abs(probability - (1.0 if win else 0.0))
        samples += 1

    formatted = []
    for _, _, label in buckets:
        stats = bucket_stats[label]
        closed = stats["wins"] + stats["losses"]
        avg_predicted = (stats["predicted_sum"] / closed) if closed else 0.0
        realized = (stats["wins"] / closed) if closed else 0.0
        formatted.append({
            "label": label,
            "samples": closed,
            "wins": stats["wins"],
            "losses": stats["losses"],
            "avg_predicted_probability": round(avg_predicted, 4),
            "realized_win_rate": round(realized, 4),
            "calibration_gap": round(realized - avg_predicted, 4),
        })

    return {
        "samples": samples,
        "mean_absolute_error": round(total_abs_error / samples, 4) if samples else None,
        "buckets": formatted,
    }


def build_daily_learning_report(limit: int = 5) -> Dict[str, Any]:
    """Build a daily report focused on adaptive forecast and setup learning."""
    model = refresh_learning_model()
    buckets = model.get("buckets") or {}
    all_stats = buckets.get("ALL", {})
    top_structures: List[Dict[str, Any]] = strongest_setups(limit=limit)
    calibration = probability_calibration_summary()

    lines = [
        "📊 Daily Learning Report",
        f"Generated: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        f"Source: {OUTCOME_FILE}",
        _bucket_line("Overall", all_stats) if all_stats else "Overall: no labeled outcomes yet",
        "",
        "🏆 Strongest structures:",
    ]

    if top_structures:
        for idx, item in enumerate(top_structures, start=1):
            lines.append(f"{idx}. {_bucket_line(item.get('key', 'STRUCTURE'), item)}")
    else:
        lines.append("Not enough closed samples yet. The engine will rank structures after 3+ closed outcomes.")

    lines.extend(["", "🎯 Probability calibration:"])
    if calibration.get("samples"):
        lines.append(f"Mean abs error: {_pct(calibration.get('mean_absolute_error', 0))} across {calibration.get('samples')} closed probability samples")
        for bucket in calibration.get("buckets", []):
            if not bucket.get("samples"):
                continue
            lines.append(
                f"- {bucket['label']}: predicted {_pct(bucket['avg_predicted_probability'])}, "
                f"realized {_pct(bucket['realized_win_rate'])} "
                f"({bucket['wins']}W/{bucket['losses']}L), gap {_pct(bucket['calibration_gap'])}"
            )
    else:
        lines.append("Not enough closed outcomes with probabilities yet.")

    lines.extend([
        "",
        "🤖 Calibration notes:",
        "- Confidence is adjusted from each setup bucket's win rate and forecast accuracy.",
        "- Ranking priority favors structures with enough samples and positive realized edge.",
        "- Weak or low-accuracy structures are automatically penalized until performance improves.",
    ])

    return {
        "generated_at": model.get("generated_at"),
        "overall": all_stats,
        "strongest_structures": top_structures,
        "probability_calibration": calibration,
        "message": "\n".join(lines),
    }


def send_daily_learning_report(bot, limit: int = 5) -> Dict[str, Any]:
    report = build_daily_learning_report(limit=limit)
    if bot and hasattr(bot, "send_telegram_msg"):
        bot.send_telegram_msg(report["message"])
    return report


if __name__ == "__main__":
    print(build_daily_learning_report()["message"])
