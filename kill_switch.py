from storage import performance_summary

MAX_DRAWDOWN_R = -5  # stop trading if below this
MAX_CONSECUTIVE_LOSSES = 3


def check_kill_switch():
    stats = performance_summary()

    if stats.get("max_drawdown_r", 0) <= MAX_DRAWDOWN_R:
        return True, "Kill switch: drawdown limit hit"

    if stats.get("losses", 0) >= MAX_CONSECUTIVE_LOSSES:
        return True, "Kill switch: too many losses"

    return False, "OK"
