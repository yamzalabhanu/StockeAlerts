from __future__ import annotations

from typing import Any, Dict


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def calculate_position_size(entry, stop, account_size, risk_pct):
    if not entry or not stop:
        return 0

    risk_amount = account_size * risk_pct
    risk_per_share = abs(entry - stop)

    if risk_per_share == 0:
        return 0

    qty = risk_amount / risk_per_share
    return int(qty)


def phase5_execution_plan(
    *,
    final_score: float,
    probabilities: Dict[str, Any] | None = None,
    no_trade: Dict[str, Any] | None = None,
    execution: Dict[str, Any] | None = None,
    setup: Dict[str, Any] | None = None,
    tech: Dict[str, Any] | None = None,
    account_size: float = 100000,
    base_risk_pct: float = 0.01,
) -> Dict[str, Any]:
    """Convert Phase 4/ensemble confidence into a Phase 5 risk-action plan.

    The scanner still decides whether to alert, but this plan standardizes how
    much risk an alert deserves and when the bot should downgrade to watch-only
    because trap probability, no-trade pressure, or execution/liquidity risk is
    too high.
    """
    probabilities = probabilities or {}
    no_trade = no_trade or {}
    execution = execution or {}
    setup = setup or {}
    tech = tech or {}

    score = _safe_float(final_score)
    win_probability = _safe_float(probabilities.get("win_probability"), 0.5)
    trap_probability = _safe_float(probabilities.get("trap_probability"), 0.0)
    no_trade_score = _safe_float(no_trade.get("score"), 0.0)
    rr = _safe_float(setup.get("risk_reward") or tech.get("risk_reward"), 0.0)
    entry = _safe_float(setup.get("entry") or tech.get("entry"), 0.0)
    stop = _safe_float(setup.get("stop") or tech.get("stop"), 0.0)

    reasons: list[str] = []
    risk_multiplier = 1.0
    action = "TRADE_READY"

    if score >= 92 and win_probability >= 0.78 and trap_probability < 0.30 and no_trade_score < 35:
        risk_multiplier += 0.25
        reasons.append("elite score/probability supports modest risk increase")
    elif score < 80 or win_probability < 0.62:
        risk_multiplier -= 0.35
        action = "REDUCED_SIZE"
        reasons.append("score or win probability below full-size threshold")

    if trap_probability >= 0.45 or no_trade_score >= 50:
        action = "WATCH_ONLY"
        risk_multiplier = 0.0
        reasons.append("trap/no-trade risk blocks automated execution")
    elif trap_probability >= 0.35 or no_trade_score >= 35:
        action = "REDUCED_SIZE"
        risk_multiplier = min(risk_multiplier, 0.5)
        reasons.append("elevated trap/no-trade risk requires reduced size")

    quality = str(execution.get("quality") or "").upper()
    if quality == "BAD":
        action = "WATCH_ONLY" if action != "WATCH_ONLY" else action
        risk_multiplier = min(risk_multiplier, 0.0)
        reasons.append("bad execution quality blocks Phase 5 risk")
    elif quality == "WARNING":
        action = "REDUCED_SIZE" if action == "TRADE_READY" else action
        risk_multiplier = min(risk_multiplier, 0.65)
        reasons.append("execution warning caps risk")

    if rr and rr < 1.5:
        action = "WATCH_ONLY" if rr < 1.2 else ("REDUCED_SIZE" if action == "TRADE_READY" else action)
        risk_multiplier = 0.0 if rr < 1.2 else min(risk_multiplier, 0.5)
        reasons.append(f"risk/reward {rr:.2f}R is below Phase 5 threshold")

    risk_multiplier = max(0.0, min(1.25, risk_multiplier))
    adjusted_risk_pct = round(base_risk_pct * risk_multiplier, 5)
    position_size = calculate_position_size(entry, stop, account_size, adjusted_risk_pct) if adjusted_risk_pct else 0
    max_risk_dollars = round(account_size * adjusted_risk_pct, 2)

    if not reasons:
        reasons.append("risk checks passed at standard size")

    return {
        "phase": "PHASE_5_RISK_PLAN",
        "action": action,
        "risk_multiplier": round(risk_multiplier, 2),
        "base_risk_pct": base_risk_pct,
        "adjusted_risk_pct": adjusted_risk_pct,
        "max_risk_dollars": max_risk_dollars,
        "position_size": position_size,
        "reasons": reasons,
    }
