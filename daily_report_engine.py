import datetime as dt
from typing import Any, Dict, List

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


def build_daily_learning_report(limit: int = 5) -> Dict[str, Any]:
    """Build a daily report focused on adaptive forecast and setup learning."""
    model = refresh_learning_model()
    buckets = model.get("buckets") or {}
    all_stats = buckets.get("ALL", {})
    top_structures: List[Dict[str, Any]] = strongest_setups(limit=limit)

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
        "message": "\n".join(lines),
    }


def send_daily_learning_report(bot, limit: int = 5) -> Dict[str, Any]:
    report = build_daily_learning_report(limit=limit)
    if bot and hasattr(bot, "send_telegram_msg"):
        bot.send_telegram_msg(report["message"])
    return report


if __name__ == "__main__":
    print(build_daily_learning_report()["message"])
