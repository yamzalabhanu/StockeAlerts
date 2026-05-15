from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import broker
from config import MARKET_TZ, MAX_TRADES_PER_TRADING_DAY

AUTO_OPTION_TRADING_ENABLED = os.getenv("ENABLE_AUTO_OPTION_TRADING", "true").lower() == "true"
AUTO_OPTION_PAPER_ONLY = os.getenv("AUTO_OPTION_PAPER_ONLY", "true").lower() == "true"
OPTION_CONTRACT_QTY = int(os.getenv("OPTION_CONTRACT_QTY", "1"))
MIN_OPTION_BUY_PREMIUM = float(os.getenv("MIN_OPTION_BUY_PREMIUM", os.getenv("MIN_OPTION_PREMIUM", "0.50")))
OPTION_PROFIT_TARGET_PCT = float(os.getenv("OPTION_PROFIT_TARGET_PCT", "50"))

OPTION_STOP_LOSS_PCT = float(os.getenv("OPTION_STOP_LOSS_PCT", "-50"))
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
    buy_order_id: Optional[str] = None
    filled_avg_price: Optional[float] = None
    filled_at: Optional[str] = None


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


def _nested_mapping_value(container: Mapping[str, Any], section: str, *names: str) -> Any:
    nested = container.get(section)
    if not isinstance(nested, Mapping):
        return None
    for name in names:
        value = nested.get(name)
        if value not in (None, ""):
            return value
    return None


def _option_premium_checks(contract: Mapping[str, Any]) -> list[tuple[str, float]]:
    """Return all positive premium references available before submitting a buy.

    A contract can appear tradable at the ask while its mark, bid, or last trade is
    already under the configured penny-option floor.  Treat every available
    positive premium reference as a guardrail so we do not submit orders for
    contracts that are already showing sub-minimum prices in any common field.
    """
    checks: list[tuple[str, float]] = []
    seen: set[str] = set()
    field_sources: tuple[tuple[str, Any], ...] = (
        ("ask", contract.get("ask")),
        ("mid", contract.get("mid")),
        ("bid", contract.get("bid")),
        ("mark", contract.get("mark") or contract.get("mark_price")),
        ("last", contract.get("last") or contract.get("last_price")),
        ("last_quote.ask", _nested_mapping_value(contract, "last_quote", "ask", "ask_price", "ap")),
        ("last_quote.bid", _nested_mapping_value(contract, "last_quote", "bid", "bid_price", "bp")),
        ("last_trade.price", _nested_mapping_value(contract, "last_trade", "price", "p")),
        ("day.close", _nested_mapping_value(contract, "day", "close", "c")),
        ("day.vwap", _nested_mapping_value(contract, "day", "vwap", "vw")),
    )
    for label, raw_value in field_sources:
        value = _safe_float(raw_value)
        if value <= 0 or label in seen:
            continue
        checks.append((label, value))
        seen.add(label)
    return checks


def _below_minimum_premium_check(contract: Mapping[str, Any]) -> Optional[tuple[str, float]]:
    for label, premium in _option_premium_checks(contract):
        if premium < MIN_OPTION_BUY_PREMIUM:
            return label, premium
    return None


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


def _response_field(response: Any, *names: str) -> Any:
    """Read a field from an Alpaca response object, mapping, or string repr."""
    if response is None:
        return None
    if isinstance(response, Mapping):
        for name in names:
            if response.get(name) not in (None, ""):
                return response.get(name)
    for name in names:
        value = getattr(response, name, None)
        if value not in (None, ""):
            return value

    text = str(response or "")
    for name in names:
        patterns = (
            rf"{re.escape(name)}=UUID\('([^']+)'\)",
            rf"{re.escape(name)}=['\"]([^'\"]+)['\"]",
            rf"['\"]{re.escape(name)}['\"]\s*:\s*['\"]?([^,'\"}}]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
    return None


def _order_id_from_response(response: Any) -> Optional[str]:
    value = _response_field(response, "id", "order_id", "client_order_id")
    return str(value).strip() if value else None


def _filled_price_from_response(response: Any) -> float:
    for name in ("filled_avg_price", "average_fill_price", "avg_fill_price"):
        value = _safe_float(_response_field(response, name))
        if value > 0:
            return value
    return 0.0


def _filled_at_from_response(response: Any) -> Optional[str]:
    value = _response_field(response, "filled_at", "updated_at", "submitted_at")
    return str(value) if value else None


def _order_is_filled(response: Any) -> bool:
    status = str(_response_field(response, "status") or "").lower()
    return status == "filled" or _filled_price_from_response(response) > 0


def _alpaca_order_by_id(order_id: Optional[str]) -> Any:
    if not order_id or broker.client is None:
        return None
    try:
        return broker.client.get_order_by_id(order_id)
    except Exception as exc:
        print(f"Alpaca order fetch failed for {order_id}: {exc}")
        return None


def _alpaca_position_entry_prices() -> dict[str, float]:
    if broker.client is None:
        return {}
    try:
        positions = broker.client.get_all_positions()
    except Exception as exc:
        print(f"Alpaca position entry fetch failed: {exc}")
        return {}

    prices: dict[str, float] = {}
    for position in positions or []:
        symbol = _position_symbol(position)
        if isinstance(position, Mapping):
            entry = _safe_float(position.get("avg_entry_price"))
        else:
            entry = _safe_float(getattr(position, "avg_entry_price", None))
        if symbol and entry > 0:
            prices[symbol] = entry
    return prices


def _resolve_filled_entry_price(position: dict[str, Any], *, symbol: str) -> tuple[float, Optional[str]]:
    """Return the actual filled buy price for a tracked option when available."""
    stored_fill = _safe_float(position.get("filled_avg_price"))
    if stored_fill > 0:
        return stored_fill, position.get("filled_at")

    order = _alpaca_order_by_id(position.get("buy_order_id"))
    filled_price = _filled_price_from_response(order)
    if filled_price > 0 and _order_is_filled(order):
        return filled_price, _filled_at_from_response(order)

    alpaca_symbol = broker.normalize_option_symbol(symbol)
    entry_prices = _alpaca_position_entry_prices()
    position_entry = _safe_float(entry_prices.get(symbol) or entry_prices.get(alpaca_symbol))
    if position_entry > 0:
        return position_entry, _now_iso()

    legacy_entry = _safe_float(position.get("entry_premium"))
    if legacy_entry > 0:
        return legacy_entry, position.get("filled_at")

    return 0.0, None




def missing_option_contract_order_details(option_contract: Mapping[str, Any] | Any) -> list[str]:
    """Return missing fields that make a recommendation unsuitable for alerts/orders."""
    contract = _contract_dict(option_contract)
    missing: list[str] = []
    if contract.get("status") != "OK":
        missing.append("status=OK")
    if not str(contract.get("contract_symbol") or "").strip():
        missing.append("contract_symbol")
    if str(contract.get("option_type") or "").upper() not in {"CALL", "PUT"}:
        missing.append("option_type")
    if _safe_float(contract.get("strike")) <= 0:
        missing.append("strike")
    if not str(contract.get("expiry") or "").strip():
        missing.append("expiry")
    if _safe_float(contract.get("ask") or contract.get("mid")) <= 0:
        missing.append("ask_or_mid")
    return missing


def has_valid_option_contract_order_details(option_contract: Mapping[str, Any] | Any) -> bool:
    """Return True only when an option recommendation has orderable contract details."""
    return not missing_option_contract_order_details(option_contract)


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
    below_floor = _below_minimum_premium_check(contract)
    if below_floor:
        premium_label, premium_value = below_floor
        _send(
            telegram_sender,
            f"🧾 Option buy skipped for {ticker}: {symbol} {premium_label} ${premium_value:.2f} is below "
            f"the ${MIN_OPTION_BUY_PREMIUM:.2f} minimum premium",
        )
        return None
    if limit_price < MIN_OPTION_BUY_PREMIUM:
        _send(
            telegram_sender,
            f"🧾 Option buy skipped for {ticker}: {symbol} limit ${limit_price:.2f} is below "
            f"the ${MIN_OPTION_BUY_PREMIUM:.2f} minimum premium",
        )
        return None

    state = _load_state(state_path)
    existing = (state.get("positions") or {}).get(symbol)
    if existing and existing.get("status") in {"OPEN", "PENDING_FILL"}:
        _send(telegram_sender, f"🧾 Option buy skipped for {ticker}: {symbol} already tracked as {existing.get('status')}")
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

    filled_price = _filled_price_from_response(response)
    order_id = _order_id_from_response(response)
    status = "OPEN" if filled_price > 0 else "PENDING_FILL"
    position = ManagedOptionPosition(
        ticker=ticker,
        direction=direction,
        contract_symbol=symbol,
        qty=qty,
        entry_premium=filled_price,
        status=status,
        opened_at=_now_iso(),
        last_order_response=str(response),
        submitted_price=limit_price,
        buy_order_id=order_id,
        filled_avg_price=filled_price if filled_price > 0 else None,
        filled_at=_filled_at_from_response(response) if filled_price > 0 else None,
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
        f"Submitted price: ${limit_price:.2f}\n"
        f"Filled price tracked: "
        f"{f'${filled_price:.2f}' if filled_price > 0 else 'pending broker fill'}\n"
        f"Exit plan: check every {OPTION_PRICE_CHECK_INTERVAL_SEC // 60} min; "
        f"take profit +{OPTION_PROFIT_TARGET_PCT:.0f}% / stop {OPTION_STOP_LOSS_PCT:.0f}% from filled price\n"
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
    """Check filled paper option prices and sell at +50% profit or -50% loss."""
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
        if position.get("status") not in {"OPEN", "PENDING_FILL"}:
            continue

        alpaca_symbol = broker.normalize_option_symbol(symbol)
        entry, filled_at = _resolve_filled_entry_price(position, symbol=symbol)
        qty = int(_safe_float(position.get("qty"), OPTION_CONTRACT_QTY))
        if entry <= 0 or qty <= 0:
            position["last_checked_at"] = _now_iso()
            continue

        if position.get("status") == "PENDING_FILL" or _safe_float(position.get("entry_premium")) <= 0:
            position.update(
                {
                    "status": "OPEN",
                    "entry_premium": round(entry, 2),
                    "filled_avg_price": round(entry, 2),
                    "filled_at": filled_at or _now_iso(),
                }
            )
            _send(
                telegram_sender,
                "✅ Alpaca paper BUY filled; monitoring actual fill price\n"
                f"Ticker: {position.get('ticker')} | Contract: {symbol}\n"
                f"Filled price: ${entry:.2f}\n"
                f"Exit plan: take profit +{OPTION_PROFIT_TARGET_PCT:.0f}% / "
                f"stop {OPTION_STOP_LOSS_PCT:.0f}% from filled price",
            )

        current = _safe_float(prices.get(symbol) or prices.get(alpaca_symbol))
        if current <= 0:
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
