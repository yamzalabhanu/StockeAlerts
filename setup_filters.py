from bot_utils import safe_float


REJECT = 'REJECT'
WARNING = 'WARNING'
PASS = 'PASS'


def evaluate_setup_quality(tech: dict, direction: str) -> dict:
    distance_from_vwap = safe_float(tech.get('distance_from_vwap'))
    distance_from_ema21 = safe_float(tech.get('distance_from_ema21'))
    breakout_distance_atr = safe_float(tech.get('breakout_distance_atr'))
    candle_body_pct = safe_float(tech.get('candle_body_pct'))
    rel_volume = safe_float(tech.get('rel_volume'))
    wick_ratio = safe_float(tech.get('wick_ratio'))
    sector_strength = safe_float(tech.get('sector_strength'))
    nearby_resistance = safe_float(tech.get('nearby_resistance_distance'))

    score = 0
    reasons = []
    warnings = []

    # Healthy structure
    if candle_body_pct is not None and candle_body_pct >= 60:
        score += 15
        reasons.append('Strong candle structure')

    # Strong RVOL
    if rel_volume is not None:
        if rel_volume >= 2:
            score += 15
            reasons.append(f'Strong RVOL {rel_volume:.1f}x')
        elif rel_volume < 0.8:
            score -= 15
            warnings.append('Weak RVOL')

    # VWAP extension
    if distance_from_vwap is not None:
        if abs(distance_from_vwap) > 2:
            score -= 20
            warnings.append('Extended from VWAP')
        elif abs(distance_from_vwap) < 1:
            score += 10

    # EMA extension
    if distance_from_ema21 is not None:
        if abs(distance_from_ema21) > 2:
            score -= 15
            warnings.append('Extended from EMA21')

    # Late breakout detection
    if breakout_distance_atr is not None:
        if breakout_distance_atr > 1:
            score -= 20
            warnings.append('Late breakout chase')
        elif breakout_distance_atr < 0.5:
            score += 10

    # Weak candle rejection
    if wick_ratio is not None and wick_ratio > 2:
        score -= 15
        warnings.append('Large wick rejection')

    # Weak sector
    if sector_strength is not None:
        if sector_strength >= 70:
            score += 10
            reasons.append('Strong sector alignment')
        elif sector_strength < 40:
            score -= 15
            warnings.append('Weak sector alignment')

    # Breakout into resistance
    if nearby_resistance is not None and nearby_resistance < 1:
        score -= 15
        warnings.append('Breakout directly into resistance')

    if score >= 25:
        status = PASS
    elif score >= 5:
        status = WARNING
    else:
        status = REJECT

    return {
        'status': status,
        'score': score,
        'reasons': reasons,
        'warnings': warnings,
    }


def should_reject_setup(result: dict) -> bool:
    return result.get('status') == REJECT
