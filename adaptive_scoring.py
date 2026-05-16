import json
import os

ADAPTIVE_FILE = "adaptive_weights.json"

DEFAULT_WEIGHTS = {
    "BREAKOUT": 0,
    "RETEST": 0,
    "MOMENTUM": 0,
    "PULLBACK": 0,
    "LATE_BREAKOUT": 0,
    "FAKE_BREAKOUT": 0,
    "LOW_RR": 0,
    "CHOP": 0,
}


def load_weights():
    if not os.path.exists(ADAPTIVE_FILE):
        return dict(DEFAULT_WEIGHTS)

    with open(ADAPTIVE_FILE, "r") as f:
        weights = json.load(f)
    merged = dict(DEFAULT_WEIGHTS)
    merged.update(weights or {})
    return merged


def save_weights(weights):
    with open(ADAPTIVE_FILE, "w") as f:
        json.dump(weights, f, indent=2, sort_keys=True)


def update_weights(entry_mode, outcome):
    """Update setup-mode weights based on outcome.

    outcome: WIN / LOSS.  Losses increase negative penalties while wins earn
    back trust, creating lightweight reinforcement-style self-correction.
    """
    weights = load_weights()
    entry_mode = str(entry_mode or "UNKNOWN").upper()

    if entry_mode not in weights:
        weights[entry_mode] = 0

    if str(outcome).upper() == "WIN":
        weights[entry_mode] += 2
    elif str(outcome).upper() == "LOSS":
        weights[entry_mode] -= 2

    weights[entry_mode] = max(min(weights[entry_mode], 25), -25)

    save_weights(weights)
    return weights


def update_behavior_penalties(outcome_context: dict, outcome: str):
    """Adapt penalties for recurring failure modes such as late breakouts.

    Example context keys: late_breakout_risk, market_phase, risk_reward,
    entry_mode.  The returned weights can be added directly to setup score; a
    negative LATE_BREAKOUT weight automatically makes future chase entries less
    aggressive after losses.
    """
    context = outcome_context or {}
    outcome = str(outcome or "").upper()
    weights = load_weights()
    loss_delta = -5 if outcome == "LOSS" else 2 if outcome == "WIN" else 0
    if not loss_delta:
        return weights

    if context.get("late_breakout_risk") or float(context.get("atr_extension") or 0) >= 1.5:
        weights["LATE_BREAKOUT"] = max(-35, min(15, weights.get("LATE_BREAKOUT", 0) + loss_delta))
    if str(context.get("market_phase") or "").upper() in {"FAKE_BREAKOUT", "EXHAUSTION"}:
        weights["FAKE_BREAKOUT"] = max(-35, min(15, weights.get("FAKE_BREAKOUT", 0) + loss_delta))
    if str(context.get("market_phase") or "").upper() in {"RANGE", "CHOP", "CHOPPY"}:
        weights["CHOP"] = max(-35, min(15, weights.get("CHOP", 0) + loss_delta))
    if float(context.get("risk_reward") or 0) and float(context.get("risk_reward") or 0) < 1.5:
        weights["LOW_RR"] = max(-35, min(15, weights.get("LOW_RR", 0) + loss_delta))

    save_weights(weights)
    return weights


def get_weight(entry_mode):
    weights = load_weights()
    return weights.get(str(entry_mode or "").upper(), 0)


def behavior_penalty(context: dict) -> int:
    context = context or {}
    weights = load_weights()
    total = 0
    if context.get("late_breakout_risk") or float(context.get("atr_extension") or 0) >= 1.5:
        total += weights.get("LATE_BREAKOUT", 0)
    if str(context.get("market_phase") or "").upper() in {"FAKE_BREAKOUT", "EXHAUSTION"}:
        total += weights.get("FAKE_BREAKOUT", 0)
    if str(context.get("market_phase") or "").upper() in {"RANGE", "CHOP", "CHOPPY"}:
        total += weights.get("CHOP", 0)
    if float(context.get("risk_reward") or 0) and float(context.get("risk_reward") or 0) < 1.5:
        total += weights.get("LOW_RR", 0)
    return max(-50, min(25, int(total)))
