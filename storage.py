import json
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_FILE = Path("results.json")


def _read_json() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        DATA_FILE.write_text("[]")
    try:
        return json.loads(DATA_FILE.read_text())
    except json.JSONDecodeError:
        return []


def _write_json(data: list[dict[str, Any]]):
    DATA_FILE.write_text(json.dumps(data, indent=2, default=str))


def save_result(result: dict):
    data = _read_json()
    result.setdefault("id", len(data) + 1)
    result.setdefault("created_at", datetime.utcnow().isoformat())
    result.setdefault("status", "OPEN")
    data.append(result)
    _write_json(data)
    return result


def load_results():
    return _read_json()


def update_trade_outcome(trade_id: int, exit_price: float, outcome: str | None = None):
    data = _read_json()
    for trade in data:
        if int(trade.get("id", -1)) == int(trade_id):
            entry = float(trade.get("price") or trade.get("entry_price") or 0)
            stop = float(trade.get("stop") or 0)
            direction = trade.get("direction", "LONG")

            risk = abs(entry - stop) if stop else 0
            pnl = (exit_price - entry) if direction == "LONG" else (entry - exit_price)
            r_multiple = round(pnl / risk, 2) if risk else 0

            trade.update({
                "exit_price": exit_price,
                "pnl": round(pnl, 2),
                "r_multiple": r_multiple,
                "outcome": outcome or ("WIN" if pnl > 0 else "LOSS"),
                "status": "CLOSED",
                "closed_at": datetime.utcnow().isoformat(),
            })
            _write_json(data)
            return trade
    raise ValueError(f"Trade id {trade_id} not found")


def performance_summary():
    data = _read_json()
    closed = [d for d in data if d.get("status") == "CLOSED"]
    wins = [d for d in closed if d.get("outcome") == "WIN"]
    losses = [d for d in closed if d.get("outcome") == "LOSS"]

    total_r = sum(float(d.get("r_multiple", 0)) for d in closed)
    avg_r = round(total_r / len(closed), 2) if closed else 0
    win_rate = round((len(wins) / len(closed)) * 100, 2) if closed else 0

    equity_curve = []
    running_r = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for d in closed:
        running_r += float(d.get("r_multiple", 0))
        peak = max(peak, running_r)
        max_drawdown = min(max_drawdown, running_r - peak)
        equity_curve.append({
            "id": d.get("id"),
            "symbol": d.get("symbol"),
            "running_r": round(running_r, 2),
            "date": d.get("closed_at") or d.get("created_at"),
        })

    by_symbol = {}
    for d in closed:
        symbol = d.get("symbol", "UNKNOWN")
        by_symbol.setdefault(symbol, {"trades": 0, "wins": 0, "total_r": 0.0})
        by_symbol[symbol]["trades"] += 1
        by_symbol[symbol]["wins"] += 1 if d.get("outcome") == "WIN" else 0
        by_symbol[symbol]["total_r"] += float(d.get("r_multiple", 0))

    for symbol, stats in by_symbol.items():
        stats["win_rate"] = round((stats["wins"] / stats["trades"]) * 100, 2) if stats["trades"] else 0
        stats["total_r"] = round(stats["total_r"], 2)

    return {
        "total_signals": len(data),
        "closed_trades": len(closed),
        "open_trades": len([d for d in data if d.get("status") == "OPEN"]),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_r": round(total_r, 2),
        "avg_r": avg_r,
        "max_drawdown_r": round(max_drawdown, 2),
        "by_symbol": by_symbol,
        "equity_curve": equity_curve,
    }
