from bot_utils import safe_float

GOOD = 'GOOD'
WARNING = 'WARNING'
BAD = 'BAD'


def evaluate_execution_quality(tech: dict) -> dict:
    tech = tech or {}

    spread_pct = safe_float(tech.get('spread_pct'))
    rel_volume = safe_float(tech.get('rel_volume'))
    candle_body_pct = safe_float(tech.get('candle_body_pct'))
    bid_ask_imbalance = safe_float(tech.get('bid_ask_imbalance'))
    distance_from_vwap = safe_float(tech.get('distance_from_vwap'))

    score = 0
    warnings = []
    strengths = []

    if spread_pct is not None:
        if spread_pct <= 0.15:
            score += 15
            strengths.append(f'Tight spread {spread_pct:.2f}%')
        elif spread_pct <= 0.4:
            score += 5
        else:
            score -= 15
            warnings.append(f'Wide spread {spread_pct:.2f}%')

    if rel_volume is not None:
        if rel_volume >= 2:
            score += 15
            strengths.append(f'Strong RVOL {rel_volume:.1f}x')
        elif rel_volume < 0.8:
            score -= 10
            warnings.append('Weak volume participation')

    if candle_body_pct is not None:
        if candle_body_pct >= 60:
            score += 12
            strengths.append('Strong candle conviction')
        elif candle_body_pct < 35:
            score -= 10
            warnings.append('Weak candle body')

    if bid_ask_imbalance is not None:
        if bid_ask_imbalance > 0.2:
            score += 10
            strengths.append('Bullish order flow imbalance')
        elif bid_ask_imbalance < -0.2:
            score -= 10
            warnings.append('Bearish order flow imbalance')

    if distance_from_vwap is not None:
        if abs(distance_from_vwap) > 2.5:
            score -= 15
            warnings.append('Price extended far from VWAP')
        elif abs(distance_from_vwap) < 1.0:
            score += 8
            strengths.append('Healthy VWAP proximity')

    if score >= 25:
        quality = GOOD
    elif score >= 5:
        quality = WARNING
    else:
        quality = BAD

    return {
        'quality': quality,
        'score': score,
        'strengths': strengths,
        'warnings': warnings,
    }


def should_reject_trade(execution: dict) -> bool:
    execution = execution or {}
    return execution.get('quality') == BAD
