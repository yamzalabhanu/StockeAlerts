import csv
import os
from collections import defaultdict

ATTRIBUTION_FILE = 'trade_attribution.csv'

FIELDS = [
    'ticker',
    'direction',
    'setup_type',
    'market_regime',
    'entry_time',
    'rvol',
    'vix',
    'spread_pct',
    'distance_from_vwap',
    'distance_from_ema21',
    'sector_strength',
    'score',
    'risk_reward',
    'pnl_r',
    'drawdown_r',
    'result',
]


def log_trade_attribution(data: dict):
    file_exists = os.path.exists(ATTRIBUTION_FILE)

    with open(ATTRIBUTION_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)

        if not file_exists:
            writer.writeheader()

        writer.writerow({k: data.get(k) for k in FIELDS})


def _safe_float(value, default=0.0):
    try:
        if value in (None, ''):
            return default
        return float(value)
    except Exception:
        return default


def _empty_stats():
    return {'wins': 0, 'losses': 0, 'total_r': 0.0, 'gross_win_r': 0.0, 'gross_loss_r': 0.0, 'drawdown_r': 0.0}


def _record(stats, key, won, pnl_r, drawdown_r):
    bucket = stats[key]
    bucket['wins' if won else 'losses'] += 1
    bucket['total_r'] += pnl_r
    if pnl_r > 0:
        bucket['gross_win_r'] += pnl_r
    elif pnl_r < 0:
        bucket['gross_loss_r'] += abs(pnl_r)
    bucket['drawdown_r'] = max(bucket.get('drawdown_r', 0.0), drawdown_r)


def _finalize(stats):
    finalized = {}
    for key, vals in stats.items():
        wins = vals.get('wins', 0)
        losses = vals.get('losses', 0)
        total = wins + losses
        gross_loss = vals.get('gross_loss_r', 0.0)
        finalized[key] = {
            **vals,
            'trades': total,
            'win_rate': round(wins / total, 4) if total else 0,
            'avg_r': round(vals.get('total_r', 0.0) / total, 3) if total else 0,
            'profit_factor': round(vals.get('gross_win_r', 0.0) / gross_loss, 3) if gross_loss else (round(vals.get('gross_win_r', 0.0), 3) if vals.get('gross_win_r', 0.0) else 0),
            'drawdown_r': round(vals.get('drawdown_r', 0.0), 3),
        }
    return finalized


def analyze_trade_performance():
    if not os.path.exists(ATTRIBUTION_FILE):
        return {}

    setup_stats = defaultdict(_empty_stats)
    regime_stats = defaultdict(_empty_stats)
    ticker_stats = defaultdict(_empty_stats)

    with open(ATTRIBUTION_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            result = str(row.get('result', '')).upper()
            won = result == 'WIN'

            setup = row.get('setup_type', 'UNKNOWN')
            regime = row.get('market_regime', 'UNKNOWN')
            ticker = row.get('ticker', 'UNKNOWN')

            pnl_r = _safe_float(row.get('pnl_r'), 1.0 if won else -1.0)
            drawdown_r = abs(_safe_float(row.get('drawdown_r'), 0.0))

            _record(setup_stats, setup, won, pnl_r, drawdown_r)
            _record(regime_stats, regime, won, pnl_r, drawdown_r)
            _record(ticker_stats, ticker, won, pnl_r, drawdown_r)

    return {
        'setup_stats': _finalize(setup_stats),
        'regime_stats': _finalize(regime_stats),
        'ticker_stats': _finalize(ticker_stats),
    }


def detect_dangerous_conditions(min_losses=5):
    stats = analyze_trade_performance()
    warnings = []

    for regime, vals in stats.get('regime_stats', {}).items():
        losses = vals.get('losses', 0)
        wins = vals.get('wins', 0)
        total = wins + losses

        if total >= min_losses and losses > wins:
            warnings.append(f'Avoid aggressive trading during {regime}')

    return warnings


def setup_attribution_adjustment(setup_type: str, min_trades: int = 8) -> dict:
    """Return a bounded score adjustment learned from setup outcomes."""
    stats = analyze_trade_performance().get('setup_stats', {})
    row = stats.get(setup_type) or stats.get(str(setup_type or '').upper())
    if not row or row.get('trades', 0) < min_trades:
        return {'adjustment': 0, 'reason': 'insufficient setup attribution history', 'stats': row or {}}

    win_rate = row.get('win_rate', 0)
    profit_factor = row.get('profit_factor', 0)
    avg_r = row.get('avg_r', 0)
    adjustment = 0
    if win_rate >= 0.7 and profit_factor >= 1.5:
        adjustment += 8
    elif win_rate >= 0.6 and avg_r > 0:
        adjustment += 4
    elif win_rate <= 0.45 or profit_factor < 0.8:
        adjustment -= 8
    elif win_rate <= 0.52:
        adjustment -= 4

    return {
        'adjustment': max(-12, min(12, adjustment)),
        'reason': f"{setup_type} win_rate={win_rate:.0%}, avg_r={avg_r:.2f}, profit_factor={profit_factor:.2f}",
        'stats': row,
    }
