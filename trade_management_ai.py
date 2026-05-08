from bot_utils import safe_float


HOLD = 'HOLD'
PARTIAL_EXIT = 'PARTIAL_EXIT'
FULL_EXIT = 'FULL_EXIT'
TRAIL_STOP = 'TRAIL_STOP'


def analyze_exit_conditions(position: dict, tech: dict, market: dict | None = None) -> dict:
    unrealized_rr = safe_float(position.get('unrealized_rr'))
    rel_volume = safe_float(tech.get('rel_volume'))
    adx = safe_float(tech.get('adx'))
    market_regime = str((market or {}).get('regime', ''))
    distance_from_vwap = safe_float(tech.get('distance_from_vwap'))
    candle_body_pct = safe_float(tech.get('candle_body_pct'))
    momentum_slope = safe_float(tech.get('momentum_slope'))
    trend_strength = safe_float(tech.get('trend_strength'))

    action = HOLD
    confidence = 50
    reasons = []

    # Hold longer in strong trend
    if adx and adx >= 25:
        confidence += 10
        reasons.append(f'Strong ADX trend {adx}')

    if rel_volume and rel_volume >= 2:
        confidence += 10
        reasons.append(f'Increasing volume {rel_volume:.1f}x')

    if market_regime in {'TRENDING_BULL', 'TRENDING_BEAR'}:
        confidence += 10
        reasons.append(f'Supportive market regime {market_regime}')

    if trend_strength and trend_strength >= 70:
        confidence += 10
        reasons.append('Trend structure strong')

    # Failed follow through
    if candle_body_pct is not None and candle_body_pct < 30:
        action = PARTIAL_EXIT
        confidence = 75
        reasons.append('Weak follow-through candle')

    # Market reversal risk
    if momentum_slope is not None and momentum_slope < -0.5:
        action = FULL_EXIT
        confidence = 85
        reasons.append('Momentum reversal detected')

    # Volume collapse
    if rel_volume is not None and rel_volume < 0.7:
        action = PARTIAL_EXIT
        confidence = max(confidence, 70)
        reasons.append('Volume collapse detected')

    # Overextended move
    if distance_from_vwap is not None and abs(distance_from_vwap) > 3:
        action = TRAIL_STOP
        confidence = max(confidence, 80)
        reasons.append('Extended from VWAP, tighten stop')

    # Lock gains at high RR
    if unrealized_rr is not None and unrealized_rr >= 3:
        action = TRAIL_STOP
        confidence = max(confidence, 85)
        reasons.append(f'High RR achieved {unrealized_rr:.1f}R')

    return {
        'action': action,
        'confidence': min(confidence, 100),
        'reasons': reasons,
    }
