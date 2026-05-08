from bot_utils import safe_float


BULLISH = {'BULLISH', 'UP', 'UPTREND'}
BEARISH = {'BEARISH', 'DOWN', 'DOWNTREND'}


def analyze_multi_timeframe_structure(tech: dict, direction: str) -> dict:
    weekly = str(tech.get('weekly_trend', '')).upper()
    daily = str(tech.get('daily_trend', '')).upper()
    h1 = str(tech.get('h1_trend', tech.get('trend_1h', ''))).upper()
    m15 = str(tech.get('m15_trend', tech.get('trend_15m', ''))).upper()
    m5 = str(tech.get('m5_trend', tech.get('trend_5m', ''))).upper()

    score = 0
    confirmations = []
    conflicts = []

    if direction == 'CALL':
        bullish_set = BULLISH

        tf_map = {
            'weekly': weekly,
            'daily': daily,
            '1H': h1,
            '15m': m15,
            '5m': m5,
        }

        weights = {
            'weekly': 20,
            'daily': 18,
            '1H': 15,
            '15m': 12,
            '5m': 10,
        }

        for tf, trend in tf_map.items():
            if trend in bullish_set:
                score += weights[tf]
                confirmations.append(f'{tf} bullish')
            elif trend:
                score -= weights[tf] * 0.7
                conflicts.append(f'{tf} bearish conflict')

    else:
        bearish_set = BEARISH

        tf_map = {
            'weekly': weekly,
            'daily': daily,
            '1H': h1,
            '15m': m15,
            '5m': m5,
        }

        weights = {
            'weekly': 20,
            'daily': 18,
            '1H': 15,
            '15m': 12,
            '5m': 10,
        }

        for tf, trend in tf_map.items():
            if trend in bearish_set:
                score += weights[tf]
                confirmations.append(f'{tf} bearish')
            elif trend:
                score -= weights[tf] * 0.7
                conflicts.append(f'{tf} bullish conflict')

    aligned = len(confirmations)

    if aligned >= 4:
        structure = 'STRONG_ALIGNMENT'
    elif aligned >= 3:
        structure = 'GOOD_ALIGNMENT'
    elif aligned >= 2:
        structure = 'MIXED_ALIGNMENT'
    else:
        structure = 'POOR_ALIGNMENT'

    return {
        'structure': structure,
        'score': round(score, 2),
        'confirmations': confirmations,
        'conflicts': conflicts,
        'aligned_timeframes': aligned,
    }


def should_allow_trade(mtf_result: dict) -> bool:
    return mtf_result.get('structure') not in {'POOR_ALIGNMENT'}
