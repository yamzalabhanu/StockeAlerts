from bot_utils import safe_float


HOLD = 'HOLD'
TRIM = 'TRIM'
SCALE = 'SCALE'
EXIT = 'EXIT'

# Backwards-compatible aliases for older callers/tests that imported the
# previous action names.
PARTIAL_EXIT = TRIM
FULL_EXIT = EXIT
TRAIL_STOP = TRIM


_DIRECTION_ALIASES = {
    'LONG': 'LONG',
    'CALL': 'LONG',
    'BULLISH': 'LONG',
    'BUY': 'LONG',
    'SHORT': 'SHORT',
    'PUT': 'SHORT',
    'BEARISH': 'SHORT',
    'SELL': 'SHORT',
}


def _normalize_direction(value):
    return _DIRECTION_ALIASES.get(str(value or 'LONG').upper(), 'LONG')


def _directional_slope(value, direction):
    value = safe_float(value)
    return value if direction == 'LONG' else -value


def _directional_distance(value, direction):
    value = safe_float(value)
    return value if direction == 'LONG' else -value


def _score_band(score):
    if score >= 75:
        return 'HIGH'
    if score >= 45:
        return 'MEDIUM'
    return 'LOW'


def _projection_decay(position, tech):
    """Estimate how much the original edge has decayed since entry.

    Accepts flexible keys because callers may store projections either on the
    open position or on the latest technical context.
    """
    current_projection = tech.get('projection') or tech.get('current_projection') or {}
    entry_projection = position.get('entry_projection') or position.get('projection_at_entry') or {}

    entry_confidence = safe_float(
        position.get('entry_projection_confidence')
        or entry_projection.get('confidence'),
        None,
    )
    current_confidence = safe_float(
        tech.get('projection_confidence')
        or current_projection.get('confidence'),
        None,
    )

    decay = 0.0
    reasons = []

    if entry_confidence is not None and current_confidence is not None:
        confidence_decay = max(0.0, entry_confidence - current_confidence)
        decay += min(confidence_decay * 1.2, 45)
        if confidence_decay >= 15:
            reasons.append(f'Projection confidence decayed {confidence_decay:.0f} pts')

    direction = _normalize_direction(position.get('direction'))
    current_direction = str(
        tech.get('projection_direction')
        or current_projection.get('direction')
        or ''
    ).upper()
    if current_direction:
        aligned = (
            direction == 'LONG' and current_direction in {'BULLISH', 'UP', 'LONG', 'CALL'}
        ) or (
            direction == 'SHORT' and current_direction in {'BEARISH', 'DOWN', 'SHORT', 'PUT'}
        )
        opposing = (
            direction == 'LONG' and current_direction in {'BEARISH', 'DOWN', 'SHORT', 'PUT'}
        ) or (
            direction == 'SHORT' and current_direction in {'BULLISH', 'UP', 'LONG', 'CALL'}
        )
        if opposing:
            decay += 35
            reasons.append(f'Projection flipped against trade: {current_direction}')
        elif aligned:
            decay -= 10
            reasons.append(f'Projection still aligned: {current_direction}')

    projected_remaining = safe_float(
        tech.get('projected_remaining_pct')
        or current_projection.get('remaining_move_pct'),
        None,
    )
    realized_move = safe_float(position.get('realized_move_pct') or tech.get('realized_move_pct'), None)
    if projected_remaining is not None and projected_remaining < 0.4 and realized_move is not None and realized_move > 1:
        decay += 20
        reasons.append('Most projected move already realized')

    return max(0, min(decay, 100)), reasons


def analyze_exit_conditions(position: dict, tech: dict, market: dict | None = None) -> dict:
    """Dynamically manage exits for open trades.

    The exit AI scores five dimensions requested by the strategy layer:
    trend continuation, volume, market regime, exhaustion, and projection decay.
    It returns HOLD, TRIM, SCALE, or EXIT so winners can be held when the edge is
    still expanding and reduced when the edge is fading.
    """
    position = position or {}
    tech = tech or {}
    market = market or {}

    direction = _normalize_direction(position.get('direction'))
    unrealized_rr = safe_float(position.get('unrealized_rr'))
    max_rr = safe_float(position.get('max_unrealized_rr') or position.get('max_rr'))
    rel_volume = safe_float(tech.get('rel_volume'))
    adx = safe_float(tech.get('adx'))
    market_regime = str(market.get('regime') or market.get('market_regime') or '').upper()
    distance_from_vwap = _directional_distance(tech.get('distance_from_vwap'), direction)
    candle_body_pct = safe_float(tech.get('candle_body_pct'), None)
    momentum_slope = _directional_slope(tech.get('momentum_slope'), direction)
    trend_strength = safe_float(tech.get('trend_strength'))
    rsi = safe_float(tech.get('rsi'), None)
    volume_trend = str(tech.get('volume_trend') or '').upper()
    exhaustion_input = safe_float(tech.get('exhaustion_score'), None)

    reasons = []
    warnings = []

    trend_score = 0
    if adx >= 30:
        trend_score += 30
        reasons.append(f'Power trend ADX {adx:.1f}')
    elif adx >= 25:
        trend_score += 24
        reasons.append(f'Strong ADX trend {adx:.1f}')
    elif adx >= 20:
        trend_score += 12
    elif adx:
        warnings.append(f'Weak trend ADX {adx:.1f}')

    if trend_strength >= 80:
        trend_score += 32
        reasons.append('Trend structure accelerating')
    elif trend_strength >= 65:
        trend_score += 24
        reasons.append('Trend structure intact')
    elif trend_strength:
        trend_score += 8

    if momentum_slope > 0.7:
        trend_score += 25
        reasons.append('Momentum slope supports continuation')
    elif momentum_slope > 0:
        trend_score += 12
    elif momentum_slope < -0.5:
        trend_score -= 35
        warnings.append('Momentum reversal detected')

    trend_score = max(0, min(trend_score, 100))

    volume_score = 45
    if rel_volume >= 2:
        volume_score = 85
        reasons.append(f'Expansion volume {rel_volume:.1f}x')
    elif rel_volume >= 1.3:
        volume_score = 68
        reasons.append(f'Volume confirms move {rel_volume:.1f}x')
    elif rel_volume and rel_volume < 0.7:
        volume_score = 18
        warnings.append('Volume collapse detected')

    if volume_trend in {'RISING', 'EXPANDING', 'ACCELERATING'}:
        volume_score = min(volume_score + 12, 100)
        reasons.append('Volume trend expanding')
    elif volume_trend in {'FALLING', 'FADING', 'CONTRACTING'}:
        volume_score = max(volume_score - 18, 0)
        warnings.append('Volume trend fading')

    supportive_regimes = {'TRENDING_BULL'} if direction == 'LONG' else {'TRENDING_BEAR'}
    opposing_regimes = {'TRENDING_BEAR'} if direction == 'LONG' else {'TRENDING_BULL'}

    if market_regime in supportive_regimes:
        regime_score = 88
        reasons.append(f'Regime aligned: {market_regime}')
    elif market_regime in opposing_regimes:
        regime_score = 15
        warnings.append(f'Regime flipped against trade: {market_regime}')
    elif market_regime in {'CHOPPY', 'HIGH_VOL'}:
        regime_score = 35
        warnings.append(f'Regime reduces hold edge: {market_regime}')
    else:
        regime_score = 50

    if exhaustion_input is not None:
        exhaustion_score = max(0, min(exhaustion_input, 100))
    else:
        exhaustion_score = 0
        if rsi is not None:
            if direction == 'LONG' and rsi >= 78:
                exhaustion_score += 35
            elif direction == 'SHORT' and rsi <= 22:
                exhaustion_score += 35
            elif direction == 'LONG' and rsi >= 70:
                exhaustion_score += 18
            elif direction == 'SHORT' and rsi <= 30:
                exhaustion_score += 18
        if distance_from_vwap > 3:
            exhaustion_score += 25
        if candle_body_pct is not None and candle_body_pct < 30:
            exhaustion_score += 20
        if max_rr and unrealized_rr and max_rr - unrealized_rr >= 0.8:
            exhaustion_score += 25

    exhaustion_score = max(0, min(exhaustion_score, 100))
    if exhaustion_score >= 70:
        warnings.append('Exhaustion risk is high')
    elif exhaustion_score >= 45:
        warnings.append('Exhaustion risk is building')

    decay_score, decay_reasons = _projection_decay(position, tech)
    warnings.extend(decay_reasons[:2] if decay_score >= 25 else [])
    if decay_score < 25:
        reasons.extend(decay_reasons[:1])

    continuation_edge = (
        trend_score * 0.35
        + volume_score * 0.22
        + regime_score * 0.23
        + (100 - exhaustion_score) * 0.12
        + (100 - decay_score) * 0.08
    )

    action = HOLD
    confidence = max(45, min(95, continuation_edge))

    # Hard exit conditions first: reversal/regime/projection failures beat a
    # generic trend score.
    if momentum_slope < -0.5 and (decay_score >= 45 or regime_score <= 20):
        action = EXIT
        confidence = 90
        warnings.append('Momentum and macro/projection edge both failed')
    elif exhaustion_score >= 82 and decay_score >= 35:
        action = EXIT
        confidence = 88
        warnings.append('Exhaustion plus projection decay favors full exit')
    elif decay_score >= 70:
        action = EXIT
        confidence = 86
        warnings.append('Projection edge invalidated')
    elif continuation_edge >= 78 and volume_score >= 70 and exhaustion_score < 45 and decay_score < 30:
        action = SCALE if unrealized_rr >= 0.8 else HOLD
        confidence = max(confidence, 82)
        reasons.append('Continuation edge supports holding winners')
    elif continuation_edge >= 62 and exhaustion_score < 60 and decay_score < 45:
        action = HOLD
        confidence = max(confidence, 70)
        reasons.append('Hold while trend edge remains intact')
    elif unrealized_rr >= 2 or exhaustion_score >= 55 or decay_score >= 45 or volume_score < 30:
        action = TRIM
        confidence = max(confidence, 74)
        warnings.append('Edge is fading; protect gains with a trim')
    else:
        action = HOLD
        reasons.append('No decisive exit trigger yet')

    if action == SCALE and unrealized_rr >= 3 and exhaustion_score >= 35:
        action = TRIM
        confidence = max(confidence, 82)
        warnings.append(f'High RR achieved {unrealized_rr:.1f}R; trim instead of adding')

    if action in {HOLD, SCALE} and distance_from_vwap > 3 and unrealized_rr >= 1.5:
        warnings.append('Extended from VWAP; use a tighter trailing stop')

    return {
        'action': action,
        'decision': action,
        'confidence': round(min(confidence, 100), 2),
        'reasons': reasons,
        'warnings': warnings,
        'scores': {
            'trend_continuation': round(trend_score, 2),
            'volume': round(volume_score, 2),
            'regime': round(regime_score, 2),
            'exhaustion': round(exhaustion_score, 2),
            'projection_decay': round(decay_score, 2),
            'continuation_edge': round(continuation_edge, 2),
        },
        'readable_scores': {
            'trend_continuation': _score_band(trend_score),
            'volume': _score_band(volume_score),
            'regime': _score_band(regime_score),
            'exhaustion': _score_band(exhaustion_score),
            'projection_decay': _score_band(decay_score),
        },
    }
