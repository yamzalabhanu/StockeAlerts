from __future__ import annotations

from typing import Any, Dict, Iterable

from bot_utils import safe_float
from chart_ai import score_vision_reading


CLEAN_BREAKOUT = 'CLEAN_BREAKOUT'
LATE_CHASE = 'LATE_CHASE'
WEAK_STRUCTURE = 'WEAK_STRUCTURE'
ACCUMULATION = 'ACCUMULATION'
DISTRIBUTION = 'DISTRIBUTION'
COMPRESSION = 'COMPRESSION'


def _snapshot_value(snapshot: Dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = safe_float(snapshot.get(name))
        if value is not None:
            return value
    return None


def score_vision_sequence(sequence: Iterable[Dict[str, Any]] | None, direction: str) -> dict:
    """Score chart-memory from multiple Vision/candle snapshots.

    Expected snapshots can be raw technical dictionaries or Vision readings from
    consecutive times (for example 09:35, 09:45, 09:55).  The scorer rewards
    acceleration with orderly retests and penalizes failed breakouts/exhaustion.
    """
    snapshots = [s for s in (sequence or []) if isinstance(s, dict)]
    if len(snapshots) < 2:
        return {"score": 0, "tags": [], "warnings": [], "samples": len(snapshots)}

    first = snapshots[0]
    last = snapshots[-1]
    direction = str(direction or "CALL").upper()
    score = 0
    tags: list[str] = []
    warnings: list[str] = []

    first_momentum = _snapshot_value(first, "momentum_score", "score", "candle_body_pct") or 0
    last_momentum = _snapshot_value(last, "momentum_score", "score", "candle_body_pct") or 0
    if last_momentum - first_momentum >= 12:
        score += 10
        tags.append("MOMENTUM_ACCELERATION")
    elif first_momentum - last_momentum >= 15:
        score -= 10
        warnings.append("Momentum decelerating across chart sequence")

    reclaim_seen = any(s.get("reclaim_confirmed") or s.get("retest_confirmed") for s in snapshots)
    failed_seen = any(s.get("failed_breakout") or s.get("breakout_failed") for s in snapshots)
    exhaustion_seen = any((safe_float(s.get("wick_ratio"), 0) or 0) >= 2 or (safe_float(s.get("breakout_distance_atr"), 0) or 0) >= 1.8 for s in snapshots)

    if reclaim_seen and not failed_seen:
        score += 12
        tags.append("SEQUENCE_RETEST_CONFIRMED")
    if failed_seen and not reclaim_seen:
        score -= 16
        warnings.append("Sequence shows failed breakout without reclaim")
        tags.append("SEQUENCE_FAILED_BREAKOUT")
    if exhaustion_seen:
        score -= 10
        warnings.append("Sequence shows exhaustion/extension risk")
        tags.append("SEQUENCE_EXHAUSTION")

    closes = [_snapshot_value(s, "close", "price", "last_price") for s in snapshots]
    closes = [c for c in closes if c is not None]
    if len(closes) >= 3:
        rising = all(a <= b for a, b in zip(closes, closes[1:]))
        falling = all(a >= b for a, b in zip(closes, closes[1:]))
        if (direction == "CALL" and rising) or (direction == "PUT" and falling):
            score += 8
            tags.append("SEQUENCE_TREND_CONFIRMATION")
        elif (direction == "CALL" and falling) or (direction == "PUT" and rising):
            score -= 8
            warnings.append("Sequence trend conflicts with alert direction")

    return {"score": score, "tags": tags, "warnings": warnings, "samples": len(snapshots)}


def score_chart_structure(tech: dict, direction: str) -> dict:
    candle_body_pct = safe_float(tech.get('candle_body_pct'))
    rel_volume = safe_float(tech.get('rel_volume'))
    distance_from_vwap = safe_float(tech.get('distance_from_vwap'))
    distance_from_ema21 = safe_float(tech.get('distance_from_ema21'))
    breakout_distance_atr = safe_float(tech.get('breakout_distance_atr'))
    wick_ratio = safe_float(tech.get('wick_ratio'))
    consolidation_tightness = safe_float(tech.get('consolidation_tightness'))

    score = 0
    structure_tags = []
    warnings = []
    sequence_score = score_vision_sequence(tech.get('vision_sequence') or tech.get('chart_sequence'), direction)
    score += safe_float(sequence_score.get('score'), 0) or 0
    structure_tags.extend(sequence_score.get('tags') or [])
    warnings.extend(sequence_score.get('warnings') or [])

    visual_score = None
    visual_reading = tech.get('vision_chart') or tech.get('visual_chart')
    if isinstance(visual_reading, dict):
        visual_score = score_vision_reading(visual_reading, direction)
        score += safe_float(visual_score.get('score'), 0)
        structure_tags.extend(visual_score.get('tags') or [])
        warnings.extend(visual_score.get('warnings') or [])

    # Strong breakout structure
    if candle_body_pct is not None and candle_body_pct >= 65:
        score += 15
        structure_tags.append(CLEAN_BREAKOUT)

    # Compression before breakout
    if consolidation_tightness is not None and consolidation_tightness <= 0.4:
        score += 12
        structure_tags.append(COMPRESSION)

    # Strong accumulation
    if rel_volume is not None and rel_volume >= 2.0:
        score += 12
        structure_tags.append(ACCUMULATION)

    # Healthy proximity
    if distance_from_vwap is not None and abs(distance_from_vwap) <= 1.0:
        score += 10

    if distance_from_ema21 is not None and abs(distance_from_ema21) <= 1.5:
        score += 8

    # Weak candle structure
    if wick_ratio is not None and wick_ratio >= 2.0:
        score -= 15
        warnings.append('Large wick rejection')
        structure_tags.append(WEAK_STRUCTURE)

    # Late chase detection
    if breakout_distance_atr is not None and breakout_distance_atr >= 1.0:
        score -= 18
        warnings.append('Late breakout extension')
        structure_tags.append(LATE_CHASE)

    # Overextended from VWAP
    if distance_from_vwap is not None and abs(distance_from_vwap) >= 3.0:
        score -= 15
        warnings.append('Extended from VWAP')

    # Distribution detection
    if rel_volume is not None and rel_volume >= 2.0 and candle_body_pct is not None and candle_body_pct < 35:
        score -= 10
        structure_tags.append(DISTRIBUTION)
        warnings.append('High volume weak candle')

    if score >= 30:
        quality = 'ELITE'
    elif score >= 15:
        quality = 'GOOD'
    elif score >= 0:
        quality = 'NEUTRAL'
    else:
        quality = 'POOR'

    return {
        'quality': quality,
        'score': score,
        'tags': structure_tags,
        'warnings': warnings,
        'visual': visual_score or {},
        'sequence': sequence_score,
    }


def should_reject_structure(result: dict) -> bool:
    return result.get('quality') == 'POOR'
