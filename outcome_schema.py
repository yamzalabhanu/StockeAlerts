import csv
import os
from typing import Any, Dict, List

LEGACY_OUTCOME_FIELDS = [
    "timestamp",
    "ticker",
    "direction",
    "entry",
    "stop",
    "target",
    "alert_type",
    "entry_mode",
    "setup_key",
    "market_regime",
    "mtf_structure",
    "chart_structure",
    "ai_confidence",
    "calibrated_confidence",
    "score",
    "expected_move_pct",
    "result",
    "target_hit",
    "stop_hit",
    "target_time",
    "stop_time",
    "max_gain_pct",
    "max_loss_pct",
    "forecast_accuracy_pct",
]

OUTCOME_ENRICHMENT_FIELDS = [
    "market_phase",
    "time_of_day_bucket",
    "atr_extension",
    "wick_ratio",
    "candle_body_pct",
    "distance_from_vwap",
    "distance_from_ema21",
    "rel_volume",
    "spread_pct",
    "option_volume",
    "open_interest",
    "sector_relative_strength",
    "deep_ai_approval",
    "deep_ai_rejection_reason",
]

OUTCOME_FIELDS = LEGACY_OUTCOME_FIELDS + OUTCOME_ENRICHMENT_FIELDS


def _blank_outcome() -> Dict[str, Any]:
    return {field: "" for field in OUTCOME_FIELDS}


def normalize_outcome_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return an outcome row with the current canonical schema."""
    normalized = _blank_outcome()
    for key, value in row.items():
        if key in normalized:
            normalized[key] = value
    return normalized


def _row_from_values(header: List[str], values: List[str]) -> Dict[str, Any]:
    """Map CSV values to outcome fields, repairing known mixed-schema rows.

    Older local alert_outcomes.csv files may have a 13-column header, while new
    rows were appended with the 24-column outcome schema. In that case the CSV
    parser sees a malformed row even though the value order is the current
    canonical OUTCOME_FIELDS order. When the value count matches the current
    schema, prefer the canonical mapping over the stale header.
    """
    if len(values) == len(OUTCOME_FIELDS):
        return dict(zip(OUTCOME_FIELDS, values))

    if len(values) == len(LEGACY_OUTCOME_FIELDS):
        row = _blank_outcome()
        row.update(dict(zip(LEGACY_OUTCOME_FIELDS, values)))
        return row

    row = _blank_outcome()
    for idx, value in enumerate(values):
        if idx >= len(header):
            continue
        field = header[idx]
        if field in row:
            row[field] = value
    return row


def read_outcome_rows(path: str) -> List[Dict[str, Any]]:
    """Read alert outcomes without dropping rows from schema drift."""
    if not os.path.exists(path):
        return []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return []

        header = [column.strip() for column in header]
        rows = []
        for values in reader:
            if not any(str(value).strip() for value in values):
                continue
            rows.append(_row_from_values(header, values))
        return rows


def rewrite_outcome_file(path: str, rows: List[Dict[str, Any]]) -> None:
    """Rewrite an outcome CSV with the canonical header and row order."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(normalize_outcome_row(row))


def append_outcome_row(path: str, row: Dict[str, Any]) -> None:
    """Append an outcome row, migrating stale headers before writing."""
    rows = read_outcome_rows(path)
    rows.append(normalize_outcome_row(row))
    rewrite_outcome_file(path, rows)
