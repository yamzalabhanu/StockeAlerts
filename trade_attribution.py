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
    'result',
]


def log_trade_attribution(data: dict):
    file_exists = os.path.exists(ATTRIBUTION_FILE)

    with open(ATTRIBUTION_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)

        if not file_exists:
            writer.writeheader()

        writer.writerow({k: data.get(k) for k in FIELDS})


def analyze_trade_performance():
    if not os.path.exists(ATTRIBUTION_FILE):
        return {}

    setup_stats = defaultdict(lambda: {'wins': 0, 'losses': 0})
    regime_stats = defaultdict(lambda: {'wins': 0, 'losses': 0})
    ticker_stats = defaultdict(lambda: {'wins': 0, 'losses': 0})

    with open(ATTRIBUTION_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            result = str(row.get('result', '')).upper()
            won = result == 'WIN'

            setup = row.get('setup_type', 'UNKNOWN')
            regime = row.get('market_regime', 'UNKNOWN')
            ticker = row.get('ticker', 'UNKNOWN')

            target = 'wins' if won else 'losses'

            setup_stats[setup][target] += 1
            regime_stats[regime][target] += 1
            ticker_stats[ticker][target] += 1

    return {
        'setup_stats': dict(setup_stats),
        'regime_stats': dict(regime_stats),
        'ticker_stats': dict(ticker_stats),
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
