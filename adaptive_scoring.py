import json
import os

ADAPTIVE_FILE = "adaptive_weights.json"


def load_weights():
    if not os.path.exists(ADAPTIVE_FILE):
        return {"BREAKOUT": 0, "RETEST": 0, "MOMENTUM": 0, "PULLBACK": 0}

    with open(ADAPTIVE_FILE, "r") as f:
        return json.load(f)


def save_weights(weights):
    with open(ADAPTIVE_FILE, "w") as f:
        json.dump(weights, f, indent=2)


def update_weights(entry_mode, outcome):
    """Update weights based on outcome.

    outcome: WIN / LOSS
    """
    weights = load_weights()

    if entry_mode not in weights:
        weights[entry_mode] = 0

    if outcome == "WIN":
        weights[entry_mode] += 2
    elif outcome == "LOSS":
        weights[entry_mode] -= 2

    # clamp
    weights[entry_mode] = max(min(weights[entry_mode], 25), -25)

    save_weights(weights)
    return weights


def get_weight(entry_mode):
    weights = load_weights()
    return weights.get(entry_mode, 0)
