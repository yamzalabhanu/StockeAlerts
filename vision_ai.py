from bot_utils import safe_float


CLEAN_BREAKOUT = 'CLEAN_BREAKOUT'
LATE_CHASE = 'LATE_CHASE'
WEAK_STRUCTURE = 'WEAK_STRUCTURE'
ACCUMULATION = 'ACCUMULATION'
DISTRIBUTION = 'DISTRIBUTION'
COMPRESSION = 'COMPRESSION'


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
    }


def should_reject_structure(result: dict) -> bool:
    return result.get('quality') == 'POOR'
