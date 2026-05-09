from bot_utils import safe_float


def predict_2day_move(tech: dict, reasoning: dict | None = None) -> dict:
    tech = tech or {}
    reasoning = reasoning or {}
    previous_projection = reasoning.get("previous_projection") or tech.get("previous_projection") or {}

    price = safe_float(tech.get('price'))
    atr = safe_float(tech.get('atr14') or tech.get('atr'))
    rsi = safe_float(tech.get('rsi'))
    adx = safe_float(tech.get('adx'))
    rel_volume = safe_float(tech.get('rel_volume'))

    regime = (reasoning.get('regime') or {}).get('regime', 'UNKNOWN')
    mtf = (reasoning.get('mtf') or {}).get('structure', 'UNKNOWN')
    vision = (reasoning.get('vision') or {}).get('quality', 'UNKNOWN')

    if not price:
        return {}

    if not atr:
        atr = max(price * 0.015, 1)

    bullish_score = 0
    bearish_score = 0

    if rsi >= 55:
        bullish_score += 15
    elif rsi <= 45:
        bearish_score += 15

    if adx >= 25:
        bullish_score += 10
        bearish_score += 10

    if rel_volume >= 1.5:
        bullish_score += 10
        bearish_score += 10

    if regime == 'TRENDING_BULL':
        bullish_score += 20

    if regime == 'TRENDING_BEAR':
        bearish_score += 20

    if mtf in ['GOOD_ALIGNMENT', 'STRONG_ALIGNMENT']:
        bullish_score += 15

    if vision in ['GOOD', 'ELITE']:
        bullish_score += 10

    direction = 'SIDEWAYS'

    if bullish_score > bearish_score + 10:
        direction = 'BULLISH'
    elif bearish_score > bullish_score + 10:
        direction = 'BEARISH'

    confidence = min(max(abs(bullish_score - bearish_score) + 55, 50), 95)

    prior_confidence = safe_float(previous_projection.get("confidence"), None)
    projection_decay = 0
    if prior_confidence is not None:
        projection_decay = max(0, min(100, prior_confidence - confidence))

    prior_direction = str(previous_projection.get("direction", "")).upper()
    direction_flip = bool(
        prior_direction
        and prior_direction != "SIDEWAYS"
        and direction != "SIDEWAYS"
        and prior_direction != direction
    )
    if direction_flip:
        projection_decay = max(projection_decay, 65)

    move_low = round((atr / price) * 100 * 1.2, 2)
    move_high = round((atr / price) * 100 * 2.5, 2)

    if direction == 'BULLISH':
        low_price = round(price * (1 + move_low / 100), 2)
        high_price = round(price * (1 + move_high / 100), 2)
        hold_guidance = 'Likely continuation for 2-4 days.'
        risk = 'LOW' if confidence >= 75 else 'MEDIUM'

    elif direction == 'BEARISH':
        low_price = round(price * (1 - move_high / 100), 2)
        high_price = round(price * (1 - move_low / 100), 2)
        hold_guidance = 'Downside continuation risk elevated.'
        risk = 'HIGH' if confidence >= 75 else 'MEDIUM'

    else:
        low_price = round(price * 0.99, 2)
        high_price = round(price * 1.01, 2)
        hold_guidance = 'Likely consolidation/chop.'
        risk = 'MEDIUM'

    return {
        'direction': direction,
        'confidence': confidence,
        'projected_move_pct': [move_low, move_high],
        'expected_price_range': [low_price, high_price],
        'hold_guidance': hold_guidance,
        'risk': risk,
        'projection_decay': round(projection_decay, 2),
        'direction_flip': direction_flip,
    }
