import json
import os
import pandas as pd

MODEL_FILE = "ml_setup_model.json"
DEFAULT_WIN_RATE = 0.50
MIN_SAMPLES_FOR_ADJUSTMENT = 5
MAX_SCORE_ADJUSTMENT = 12


def load_model(path=MODEL_FILE):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_model(model, path=MODEL_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2, sort_keys=True)

    from learning_replay_scheduler import maybe_run_after_learning_change

    maybe_run_after_learning_change(model_files=[path])


def result_to_win(row):
    result = str(row.get("result", row.get("outcome", ""))).strip().upper()
    if result in {"WIN", "TARGET", "TP", "TP1", "TP2", "PROFIT", "1", "TRUE"}:
        return True
    if result in {"LOSS", "STOP", "SL", "FAILED", "0", "FALSE"}:
        return False
    return None


def setup_key(row):
    entry_mode = str(row.get("entry_mode", row.get("setup_type", "UNKNOWN"))).strip().upper() or "UNKNOWN"
    direction = str(row.get("direction", "ANY")).strip().upper() or "ANY"
    return entry_mode + ":" + direction


def score_adjustment_from_win_rate(win_rate, sample_count):
    if sample_count < MIN_SAMPLES_FOR_ADJUSTMENT:
        return 0.0
    raw = (float(win_rate) - DEFAULT_WIN_RATE) * 40.0
    return round(max(-MAX_SCORE_ADJUSTMENT, min(MAX_SCORE_ADJUSTMENT, raw)), 2)


def train_from_rows(rows, model_path=MODEL_FILE):
    stats = {}
    for row in rows:
        win = result_to_win(row)
        if win is None:
            continue
        key = setup_key(row)
        if key not in stats:
            stats[key] = {"wins": 0, "losses": 0, "total": 0, "win_rate": DEFAULT_WIN_RATE}
        stats[key]["wins"] += 1 if win else 0
        stats[key]["losses"] += 0 if win else 1
        stats[key]["total"] += 1

    for key, data in stats.items():
        total = max(int(data.get("total", 0)), 1)
        data["win_rate"] = round(float(data.get("wins", 0)) / total, 4)
        data["score_adjustment"] = score_adjustment_from_win_rate(data["win_rate"], total)

    save_model(stats, model_path)
    return stats


def train_model(csv_file="alert_outcomes.csv", fallback_csv="stock_technical_alerts.csv"):
    path = csv_file if os.path.exists(csv_file) else fallback_csv
    if not os.path.exists(path):
        print(f"No training file found: {csv_file} or {fallback_csv}")
        return {}
    try:
        df = pd.read_csv(path, engine="python", on_bad_lines="skip")
    except Exception as e:
        print(f"Failed to load ML training data from {path}: {e}")
        return {}
    if df.empty:
        print("No ML training rows found.")
        return {}
    model = train_from_rows(df.to_dict(orient="records"))
    print("ML adaptive model updated:", model)
    return model


def get_setup_score(entry_mode, direction, base_score, model_path=MODEL_FILE):
    model = load_model(model_path)
    key = str(entry_mode).upper() + ":" + str(direction).upper()
    fallback_key = str(entry_mode).upper() + ":ANY"
    data = model.get(key) or model.get(fallback_key)
    if not data:
        return float(base_score)
    adjustment = float(data.get("score_adjustment", 0.0))
    return round(max(0.0, min(100.0, float(base_score) + adjustment)), 2)
