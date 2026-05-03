from collections import Counter, defaultdict
from storage import load_results


def analyze_losing_patterns(limit: int = 50):
    """Find common traits in recent losing trades so filters can be tightened."""
    trades = [t for t in load_results() if t.get("status") == "CLOSED"][-limit:]
    losses = [t for t in trades if t.get("outcome") == "LOSS"]

    if not losses:
        return {
            "loss_count": 0,
            "common_symbols": {},
            "common_signals": {},
            "avg_score": 0,
            "avg_rel_volume": 0,
            "notes": ["No recent losing trades found"],
        }

    symbols = Counter(t.get("symbol", "UNKNOWN") for t in losses)
    signals = Counter(t.get("signal", "UNKNOWN") for t in losses)
    scores = [float(t.get("score", 0)) for t in losses]
    rel_vols = []

    for t in losses:
        option = t.get("option") or {}
        if option.get("implied_volatility"):
            rel_vols.append(float(option.get("implied_volatility")))

    notes = []
    if scores and sum(scores) / len(scores) < 90:
        notes.append("Losses are coming from lower-score setups; increase min_score")
    if len(symbols) and symbols.most_common(1)[0][1] >= 2:
        notes.append(f"Repeated losses in {symbols.most_common(1)[0][0]}; consider temporary symbol blacklist")
    if len(signals) and signals.most_common(1)[0][1] >= 2:
        notes.append(f"Repeated losses in {signals.most_common(1)[0][0]}; tighten this setup type")

    return {
        "loss_count": len(losses),
        "common_symbols": dict(symbols.most_common(10)),
        "common_signals": dict(signals.most_common(10)),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "avg_option_iv": round(sum(rel_vols) / len(rel_vols), 3) if rel_vols else 0,
        "notes": notes,
    }


def should_skip_from_loss_history(symbol: str, signal: str, max_recent_symbol_losses: int = 2):
    patterns = analyze_losing_patterns()
    symbol_losses = patterns.get("common_symbols", {}).get(symbol, 0)
    signal_losses = patterns.get("common_signals", {}).get(signal, 0)

    if symbol_losses >= max_recent_symbol_losses:
        return True, f"Recent loss history: {symbol} has {symbol_losses} losses"
    if signal_losses >= 3:
        return True, f"Recent loss history: {signal} has repeated losses"

    return False, "Loss history OK"
