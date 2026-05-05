import os
import pickle
from typing import Dict, Iterable, Tuple

import pandas as pd

MODEL_FILE = "ml_logistic_model.pkl"
FEATURE_COLUMNS = [
    "score",
    "risk_reward",
    "ai_confidence",
    "intraday_confirmations",
    "current_volume",
    "avg_20_volume",
    "price_vs_vwap_pct",
    "price_vs_ema21_pct",
    "trend_5m_num",
    "trend_15m_num",
]


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _trend_to_num(value):
    value = str(value or "").upper()
    if value in {"UP", "BULLISH"}:
        return 1.0
    if value in {"DOWN", "BEARISH"}:
        return -1.0
    return 0.0


def _pct(a, b):
    a = _safe_float(a, None)
    b = _safe_float(b, None)
    if a is None or b in (None, 0):
        return 0.0
    return ((a - b) / b) * 100.0


def _label_from_row(row: Dict) -> int | None:
    result = str(row.get("result", row.get("outcome", ""))).strip().upper()
    positive = {"WIN", "TARGET", "TP", "TP1", "TP2", "PROFIT", "SUCCESS", "1", "TRUE"}
    negative = {"LOSS", "STOP", "SL", "FAILED", "FAIL", "0", "FALSE"}
    if result in positive:
        return 1
    if result in negative:
        return 0
    return None


def features_from_row(row: Dict) -> Dict[str, float]:
    price = row.get("price") or row.get("entry")
    return {
        "score": _safe_float(row.get("score")),
        "risk_reward": _safe_float(row.get("risk_reward")),
        "ai_confidence": _safe_float(row.get("ai_confidence", row.get("confidence"))),
        "intraday_confirmations": _safe_float(row.get("intraday_confirmations", row.get("confirmations"))),
        "current_volume": _safe_float(row.get("current_volume")),
        "avg_20_volume": _safe_float(row.get("avg_20_volume")),
        "price_vs_vwap_pct": _pct(price, row.get("vwap")),
        "price_vs_ema21_pct": _pct(price, row.get("ema21")),
        "trend_5m_num": _trend_to_num(row.get("trend_5m")),
        "trend_15m_num": _trend_to_num(row.get("trend_15m")),
    }


def _import_sklearn():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    return LogisticRegression, Pipeline, StandardScaler


def train_logistic_model(rows: Iterable[Dict], model_file: str = MODEL_FILE) -> Dict:
    LogisticRegression, Pipeline, StandardScaler = _import_sklearn()

    x_rows = []
    y = []
    for row in rows:
        label = _label_from_row(row)
        if label is None:
            continue
        x_rows.append(features_from_row(row))
        y.append(label)

    if len(x_rows) < 10 or len(set(y)) < 2:
        return {"trained": False, "reason": "Need at least 10 labeled rows with both outcomes", "rows": len(x_rows)}

    X = pd.DataFrame(x_rows, columns=FEATURE_COLUMNS).fillna(0.0)
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])
    model.fit(X, y)

    payload = {"model": model, "features": FEATURE_COLUMNS, "rows": len(x_rows)}
    with open(model_file, "wb") as f:
        pickle.dump(payload, f)

    return {"trained": True, "rows": len(x_rows), "features": FEATURE_COLUMNS}


def train_logistic_model_from_csv(csv_file="alert_outcomes.csv", fallback_csv="stock_technical_alerts.csv") -> Dict:
    path = csv_file if os.path.exists(csv_file) else fallback_csv
    if not os.path.exists(path):
        return {"trained": False, "reason": f"No training file found: {csv_file} or {fallback_csv}"}

    df = pd.read_csv(path, engine="python", on_bad_lines="skip")
    return train_logistic_model(df.to_dict(orient="records"))


def predict_win_probability(row: Dict, model_file: str = MODEL_FILE) -> Tuple[float | None, str]:
    if not os.path.exists(model_file):
        return None, "model not trained"

    try:
        with open(model_file, "rb") as f:
            payload = pickle.load(f)
        model = payload["model"]
        features = payload.get("features", FEATURE_COLUMNS)
        X = pd.DataFrame([features_from_row(row)], columns=features).fillna(0.0)
        probability = float(model.predict_proba(X)[0][1])
        return probability, "ok"
    except Exception as e:
        return None, f"prediction failed: {e}"


def adjust_score_with_logistic(row: Dict, base_score: float) -> Tuple[float, float | None, str]:
    probability, reason = predict_win_probability(row)
    if probability is None:
        return float(base_score), None, reason

    adjustment = (probability - 0.50) * 24.0
    adjusted = max(0.0, min(100.0, float(base_score) + adjustment))
    return round(adjusted, 2), round(probability, 4), reason
