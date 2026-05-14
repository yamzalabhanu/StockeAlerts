from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import broker
from config import MARKET_TZ, MAX_TRADES_PER_TRADING_DAY

AUTO_OPTION_TRADING_ENABLED = os.getenv("ENABLE_AUTO_OPTION_TRADING", "true").lower() == "true"
AUTO_OPTION_PAPER_ONLY = os.getenv("AUTO_OPTION_PAPER_ONLY", "true").lower() == "true"
OPTION_CONTRACT_QTY = int(os.getenv("OPTION_CONTRACT_QTY", "1"))
OPTION_PROFIT_TARGET_PCT = float(os.getenv("OPTION_PROFIT_TARGET_PCT", "20"))

OPTION_STOP_LOSS_PCT = float(os.getenv("OPTION_STOP_LOSS_PCT", "-10"))
OPTION_PRICE_CHECK_INTERVAL_SEC = int(os.getenv("OPTION_PRICE_CHECK_INTERVAL_SEC", "300"))

OPTION_ORDER_STATE_FILE = Path(os.getenv("OPTION_ORDER_STATE_FILE", "option_order_state.json"))

TelegramSender = Optional[Callable[[str], bool]]


@dataclass
class ManagedOptionPosition:
    ticker: str
    direction: str
    contract_symbol: str
    qty: int
    entry_premium: float
    status: str
    opened_at: str
    last_order_response: str = ""
    submitted_price: Optional[float] = None
    current_premium: Optional[float] = None
    last_checked_at: Optional[str] = None
    last_pnl_pct: Optional[float] = None
    closed_at: Optional[str] = None
    exit_premium: Optional[float] = None
    exit_reason: Optional[str] = None
    exit_order_response: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trading_day(value: Optional[str] = None) -> str:
    """Return the market-local trading day string used for daily trade caps."""
    if not value:
        return datetime.now(MARKET_TZ).date().isoformat()

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(MARKET_TZ).date().isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_state(path: Path = OPTION_ORDER_STATE_FILE) -> dict[str, Any]:
    if not path.exists():
        return {"positions": {}, "trade_counts": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            payload.setdefault("positions", {})
            payload.setdefault("trade_counts", {})
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    return {"positions": {}, "trade_counts": {}}


def _daily_trade_count(state: Mapping[str, Any], trading_day: Optional[str] = None) -> int:
    """Return the number of option buy trades recorded for a market-local day."""
    day = trading_day or _trading_day()
    stored_count = int((state.get("trade_counts") or {}).get(day, 0) or 0)
    position_count = 0
    for position in (state.get("positions") or {}).values():
        if _trading_day(position.get("opened_at")) == day:
            position_count += 1
    return max(stored_count, position_count)


def _increment_daily_trade_count(state: dict[str, Any], trading_day: Optional[str] = None) -> None:
    day = trading_day or _trading_day()
    counts = state.setdefault("trade_counts", {})
    counts[day] = _daily_trade_count(state, day) + 1


def _save_state(state: dict[str, Any], path: Path = OPTION_ORDER_STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True) if path.parent != Path(".") else None
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def _send(sender: TelegramSender, message: str) -> bool:
    if not sender:
        print(message)
        return False
    try:
        return bool(sender(message))
    except Exception as exc:
        print(f"Telegram confirmation failed: {exc}")
        return False


def _trading_guard() -> tuple[bool, str]:
    if not AUTO_OPTION_TRADING_ENABLED:
        return False, "ENABLE_AUTO_OPTION_TRADING is false"
    if AUTO_OPTION_PAPER_ONLY and not broker.PAPER:
        return False, "AUTO_OPTION_PAPER_ONLY blocked non-paper Alpaca execution"
    return True, "Paper options auto-trading enabled"


def _contract_dict(option_contract: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(option_contract, Mapping):
        return dict(option_contract)
    return dict(getattr(option_contract, "__dict__", {}) or {})


def _order_response_failed(response: Any) -> bool:
    text = str(response or "").strip().lower()
    return text.startswith(("option order failed", "trade failed", "blocked:"))


def maybe_buy_recommended_option(
    *,
    ticker: str,
    direction: str,
    option_contract: Mapping[str, Any] | Any,
    telegram_sender: TelegramSender = None,
    state_path: Path = OPTION_ORDER_STATE_FILE,
) -> Optional[ManagedOptionPosition]:
    """Buy the recommended option contract in Alpaca paper mode and notify Telegram."""
    contract = _contract_dict(option_contract)
    if contract.get("status") != "OK":
        return None

    allowed, guard_reason = _trading_guard()
    if not allowed:
        _send(telegram_sender, f"🧾 Option buy skipped for {ticker}: {guard_reason}")
        return None

    raw_symbol = str(contract.get("contract_symbol") or "")
    symbol = broker.normalize_option_symbol(raw_symbol)
    limit_price = _safe_float(contract.get("ask") or contract.get("mid"))
    qty = OPTION_CONTRACT_QTY
    if not symbol or limit_price <= 0 or qty <= 0:
        _send(telegram_sender, f"🧾 Option buy skipped for {ticker}: missing contract symbol, limit price, or qty")
        return None

    state = _load_state(state_path)
    existing = (state.get("positions") or {}).get(symbol)
    if existing and existing.get("status") == "OPEN":
        _send(telegram_sender, f"🧾 Option buy skipped for {ticker}: {symbol} already tracked as OPEN")
        return None

    trades_today = _daily_trade_count(state)
    if trades_today >= MAX_TRADES_PER_TRADING_DAY:
        _send(
            telegram_sender,
            f"🧾 Option buy skipped for {ticker}: daily trade cap reached "
            f"({trades_today}/{MAX_TRADES_PER_TRADING_DAY})",
        )
        return None

    response = broker.place_option_limit_order(symbol, qty, "BUY", limit_price)
    if _order_response_failed(response):
        _send(
            telegram_sender,
            "❌ Alpaca paper BUY failed\n"
            f"Ticker: {ticker} | Direction: {direction}\n"
            f"Contract: {symbol}\n"
            f"Qty: {qty} | Limit: ${limit_price:.2f}\n"
            f"Broker response: {response}",
        )
        return None

    position = ManagedOptionPosition(
        ticker=ticker,
        direction=direction,
        contract_symbol=symbol,
        qty=qty,
        entry_premium=limit_price,
        status="OPEN",
        opened_at=_now_iso(),
        last_order_response=str(response),
        submitted_price=limit_price,
    )
    _increment_daily_trade_count(state, _trading_day(position.opened_at))
    state.setdefault("positions", {})[symbol] = asdict(position)
    _save_state(state, state_path)

    _send(
        telegram_sender,
        "✅ Alpaca paper BUY submitted (DAY limit; queues after hours)\n"
        f"Ticker: {ticker} | Direction: {direction}\n"
        f"Contract: {symbol}\n"
        f"Qty: {qty} | Limit: ${limit_price:.2f}\n"
        f"Submitted price tracked: ${limit_price:.2f}\n"
        f"Exit plan: check every {OPTION_PRICE_CHECK_INTERVAL_SEC // 60} min; "
        f"take profit +{OPTION_PROFIT_TARGET_PCT:.0f}% / stop {OPTION_STOP_LOSS_PCT:.0f}%\n"
        f"Broker response: {response}",
    )
    return position


def _position_symbol(position: Any) -> str:
    return str(getattr(position, "symbol", "") or (position.get("symbol") if isinstance(position, Mapping) else ""))


def _position_market_price(position: Any) -> float:
    if isinstance(position, Mapping):
        for key in ("current_price", "market_price", "avg_entry_price"):
            value = _safe_float(position.get(key))
            if value > 0:
                return value
        market_value = _safe_float(position.get("market_value"))
        qty = abs(_safe_float(position.get("qty")))
    else:
        for key in ("current_price", "market_price", "avg_entry_price"):
            value = _safe_float(getattr(position, key, None))
            if value > 0:
                return value
        market_value = _safe_float(getattr(position, "market_value", None))
        qty = abs(_safe_float(getattr(position, "qty", None)))
    return market_value / max(qty * 100, 1) if market_value and qty else 0.0


def _alpaca_position_prices() -> dict[str, float]:
    if broker.client is None:
        print("Alpaca position fetch skipped: ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
        return {}
    try:
        positions = broker.client.get_all_positions()
    except Exception as exc:
        print(f"Alpaca position fetch failed: {exc}")
        return {}

    prices: dict[str, float] = {}
    for position in positions or []:
        symbol = _position_symbol(position)
        market_price = _position_market_price(position)
        if symbol and market_price > 0:
            prices[symbol] = market_price
    return prices


def manage_open_option_positions(
    *,
    telegram_sender: TelegramSender = None,
    state_path: Path = OPTION_ORDER_STATE_FILE,
    price_lookup: Optional[Mapping[str, float]] = None,
) -> list[dict[str, Any]]:
    """Check tracked paper option prices and sell at +20% profit or -10% loss."""
    allowed, guard_reason = _trading_guard()
    if not allowed:
        print(f"Option position management skipped: {guard_reason}")
        return []

    state = _load_state(state_path)
    positions = state.get("positions") or {}
    if not positions:
        return []

    prices = dict(price_lookup) if price_lookup is not None else _alpaca_position_prices()
    closed: list[dict[str, Any]] = []

    for symbol, position in list(positions.items()):
        if position.get("status") != "OPEN":
            continue

        entry = _safe_float(position.get("entry_premium"))
        alpaca_symbol = broker.normalize_option_symbol(symbol)
        current = _safe_float(prices.get(symbol) or prices.get(alpaca_symbol))
        qty = int(_safe_float(position.get("qty"), OPTION_CONTRACT_QTY))
        if entry <= 0 or current <= 0 or qty <= 0:
            continue

        pnl_pct = ((current - entry) / entry) * 100
        position["current_premium"] = round(current, 2)
        position["last_checked_at"] = _now_iso()
        position["last_pnl_pct"] = round(pnl_pct, 2)

        exit_reason = None
        if pnl_pct >= OPTION_PROFIT_TARGET_PCT:
            exit_reason = "TAKE_PROFIT"
        elif pnl_pct <= OPTION_STOP_LOSS_PCT:
            exit_reason = "STOP_LOSS"

        if not exit_reason:
            continue

        response = broker.place_option_limit_order(alpaca_symbol, qty, "SELL", current)
        if _order_response_failed(response):
            position["exit_order_response"] = str(response)
            _send(
                telegram_sender,
                "❌ Alpaca paper SELL failed; position remains tracked as OPEN\n"
                f"Ticker: {position.get('ticker')} | Reason: {exit_reason}\n"
                f"Contract: {symbol}\n"
                f"Qty: {qty} | Limit: ${current:.2f}\n"
                f"P/L: {pnl_pct:+.2f}% (entry ${entry:.2f})\n"
                f"Broker response: {response}",
            )
            continue

        position.update(
            {
                "status": "CLOSED",
                "closed_at": _now_iso(),
                "exit_premium": round(current, 2),
                "exit_reason": exit_reason,
                "exit_order_response": str(response),
            }
        )
        closed.append(dict(position))
        _send(
            telegram_sender,
            "✅ Alpaca paper SELL submitted\n"
            f"Ticker: {position.get('ticker')} | Reason: {exit_reason}\n"
            f"Contract: {symbol}\n"
            f"Qty: {qty} | Limit: ${current:.2f}\n"
            f"P/L: {pnl_pct:+.2f}% (entry ${entry:.2f})\n"
            f"Broker response: {response}",
        )

    _save_state(state, state_path)
    return closed
