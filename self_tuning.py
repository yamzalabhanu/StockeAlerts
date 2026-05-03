from storage import performance_summary


CONFIG = {
    "min_score": 85,
    "min_volume": 1.8
}


def adjust_strategy():
    stats = performance_summary()

    win_rate = stats.get("win_rate", 0)

    if win_rate < 55:
        CONFIG["min_score"] += 5
        CONFIG["min_volume"] += 0.2
        action = "Tightening filters"

    elif win_rate > 70:
        CONFIG["min_score"] -= 5
        CONFIG["min_volume"] -= 0.2
        action = "Relaxing filters"

    else:
        action = "No change"

    return {
        "win_rate": win_rate,
        "config": CONFIG,
        "action": action
    }
