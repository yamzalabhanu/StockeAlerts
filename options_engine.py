from __future__ import annotations

import math
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

from config import normalize_api_key

POLYGON_API_KEY = normalize_api_key(os.getenv("POLYGON_API_KEY"))
MASSIVE_API_KEY = normalize_api_key(os.getenv("MASSIVE_API_KEY")) or POLYGON_API_KEY
OPTIONS_API_KEY = normalize_api_key(os.getenv("OPTIONS_API_KEY")) or MASSIVE_API_KEY
OPTIONS_API_BASE_URL = os.getenv("OPTIONS_API_BASE_URL", "https://api.polygon.io").rstrip("/")

MIN_OPTION_VOLUME = int(os.getenv("MIN_OPTION_VOLUME", "50"))
MIN_OPTION_OI = int(os.getenv("MIN_OPTION_OI", "100"))
REQUIRE_OPTION_LIQUIDITY_FIELDS = os.getenv("REQUIRE_OPTION_LIQUIDITY_FIELDS", "false").lower() == "true"
MAX_SPREAD_PCT = float(os.getenv("MAX_OPTION_SPREAD_PCT", "12"))
MAX_IV = float(os.getenv("MAX_OPTION_IV", "1.20"))
MIN_OPTION_PREMIUM = float(os.getenv("MIN_OPTION_PREMIUM", "0.50"))
TARGET_MIN_DELTA = float(os.getenv("TARGET_MIN_DELTA", "0.40"))
TARGET_MAX_DELTA = float(os.getenv("TARGET_MAX_DELTA", "0.55"))
MIN_DTE = int(os.getenv("MIN_OPTION_DTE", "7"))
MAX_DTE = int(os.getenv("MAX_OPTION_DTE", "45"))
HIGH_VOLUME_OPTION_MIN_VOLUME = int(os.getenv("HIGH_VOLUME_OPTION_MIN_VOLUME", "10000"))
HIGH_VOLUME_OPTION_MIN_DTE = int(os.getenv("HIGH_VOLUME_OPTION_MIN_DTE", "0"))

FLOW_EXPIRY_DAYS = int(os.getenv("OPTIONS_FLOW_EXPIRY_DAYS", "45"))
FLOW_TOP_CONTRACTS = int(os.getenv("OPTIONS_FLOW_TOP_CONTRACTS", "24"))
FLOW_TRADE_LIMIT = int(os.getenv("OPTIONS_FLOW_TRADE_LIMIT", "50"))
SWEEP_NOTIONAL_THRESHOLD = float(os.getenv("OPTIONS_SWEEP_NOTIONAL_THRESHOLD", "250000"))
BLOCK_NOTIONAL_THRESHOLD = float(os.getenv("OPTIONS_BLOCK_NOTIONAL_THRESHOLD", "500000"))
PUT_WALL_OI_THRESHOLD = int(os.getenv("OPTIONS_PUT_WALL_OI_THRESHOLD", "5000"))
CALL_WALL_OI_THRESHOLD = int(os.getenv("OPTIONS_CALL_WALL_OI_THRESHOLD", "5000"))
OI_BUILD_VOLUME_OI_RATIO = float(os.getenv("OPTIONS_OI_BUILD_VOLUME_OI_RATIO", "0.35"))
IV_EXPANSION_RATIO = float(os.getenv("OPTIONS_IV_EXPANSION_RATIO", "1.15"))
DELTA_IMBALANCE_RATIO = float(os.getenv("OPTIONS_DELTA_IMBALANCE_RATIO", "1.75"))
GAMMA_SQUEEZE_MIN_SCORE = int(os.getenv("OPTIONS_GAMMA_SQUEEZE_MIN_SCORE", "70"))
OPTIONS_MAX_SNAPSHOT_AGE_SEC = int(os.getenv("OPTIONS_MAX_SNAPSHOT_AGE_SEC", "30"))


@dataclass
class OptionCandidate:
    underlying: str
    contract_symbol: str
    option_type: str
    strike: float
    expiry: str
    dte: int
    bid: Optional[float]
    ask: Optional[float]
    mid: Optional[float]
    spread_pct: Optional[float]
    delta: Optional[float]
    gamma: Optional[float]
    theta: Optional[float]
    implied_volatility: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]
    status: str
    reason: str
    recommendation_score: Optional[float] = None
    liquidity_score: Optional[float] = None
    volume_oi_ratio: Optional[float] = None
    dollar_volume: Optional[float] = None


@dataclass
class OptionsFlowSignal:
    name: str
    direction: str
    severity: int
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class OptionsFlowReport:
    underlying: str
    status: str
    score: int
    bias: str
    call_premium: float
    put_premium: float
    call_volume: int
    put_volume: int
    call_open_interest: int
    put_open_interest: int
    net_delta: float
    net_gamma: float
    avg_iv: Optional[float]
    iv_rank_proxy: Optional[float]
    max_pain_proxy: Optional[float]
    put_wall_strike: Optional[float]
    call_wall_strike: Optional[float]
    dealer_gamma_state: str
    gamma_squeeze: bool
    signals: list[OptionsFlowSignal]
    reason: str


def _next_fridays(min_dte: int = MIN_DTE, max_dte: int = MAX_DTE) -> list[str]:
    today = datetime.utcnow().date()
    dates = []
    for i in range(min_dte, max_dte + 1):
        d = today + timedelta(days=i)
        if d.weekday() == 4:
            dates.append(d.isoformat())
    return dates or [(today + timedelta(days=min_dte)).isoformat()]


def _option_side_from_signal(signal: str) -> Optional[str]:
    signal = str(signal or "").upper()
    if "CALL" in signal or "BULLISH" in signal or "UPTREND" in signal:
        return "call"
    if "PUT" in signal or "BEARISH" in signal or "DOWNTREND" in signal:
        return "put"
    return None


def _spread_pct(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid is None or ask is None or ask <= 0:
        return None
    mid = (bid + ask) / 2
    if mid <= 0:
        return None
    return ((ask - bid) / mid) * 100


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _first_present(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = mapping.get(name)
        if value not in (None, ""):
            return value
    return None


def _quote_bid(quote: dict[str, Any]) -> Any:
    return _first_present(quote, "bid", "bid_price", "bidPrice", "bp")


def _quote_ask(quote: dict[str, Any]) -> Any:
    return _first_present(quote, "ask", "ask_price", "askPrice", "ap")


def _quote_midpoint(quote: dict[str, Any]) -> Optional[float]:
    value = _first_present(quote, "midpoint", "mid", "mark", "mark_price", "markPrice")
    if value is None:
        return None
    midpoint = _safe_float(value)
    return midpoint if midpoint > 0 else None


def _quote_prices(item: dict[str, Any]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    quote = item.get("last_quote", {}) or {}
    bid = _quote_bid(quote)
    ask = _quote_ask(quote)
    bid_float = _safe_float(bid) if bid is not None else None
    ask_float = _safe_float(ask) if ask is not None else None
    midpoint = (
        (bid_float + ask_float) / 2
        if bid_float is not None and ask_float is not None
        else _quote_midpoint(quote)
    )
    return bid_float, ask_float, midpoint


def _contract_entry_price(bid: Optional[float], ask: Optional[float], mid: Optional[float]) -> float:
    """Return the premium that would be used for a buy entry."""
    if ask is not None and ask > 0:
        return ask
    if mid is not None and mid > 0:
        return mid
    if bid is not None and bid > 0:
        return bid
    return 0.0


def _round_or_none(value: Optional[float], ndigits: int = 2) -> Optional[float]:
    if value is None:
        return None
    return round(value, ndigits)


def _option_type(details: dict[str, Any]) -> str:
    return str(
        _first_present(details, "contract_type", "contractType", "type", "option_type", "optionType")
        or ""
    ).lower()


def _option_ticker(details: dict[str, Any]) -> str:
    return str(
        _first_present(
            details,
            "ticker",
            "symbol",
            "contract_symbol",
            "contractSymbol",
            "option_symbol",
            "optionSymbol",
        )
        or ""
    )


def _expiration_date(details: dict[str, Any]) -> str:
    return str(_first_present(details, "expiration_date", "expirationDate", "expiry", "expiration") or "")


def _strike(details: dict[str, Any]) -> float:
    return _safe_float(_first_present(details, "strike_price", "strikePrice", "strike"))


def _last_trade_price(item: dict[str, Any]) -> Optional[float]:
    trade = item.get("last_trade", {}) or {}
    for key in ("price", "p", "last_price"):
        value = trade.get(key)
        if value is not None:
            price = _safe_float(value)
            if price > 0:
                return price
    return None


def _day_close_price(item: dict[str, Any]) -> Optional[float]:
    day = item.get("day", {}) or {}
    for key in ("close", "last_price", "c", "vwap"):
        value = day.get(key)
        if value is not None:
            price = _safe_float(value)
            if price > 0:
                return price
    return None


def _mid_from_snapshot(item: dict[str, Any]) -> Optional[float]:
    bid_float, ask_float, midpoint = _quote_prices(item)
    if bid_float is not None and ask_float is not None:
        mid = (bid_float + ask_float) / 2
        if mid > 0:
            return mid
    return midpoint or _last_trade_price(item) or _day_close_price(item)


def _snapshot_volume(item: dict[str, Any]) -> int:
    """Return same-day option volume across Polygon/Massive-compatible fields."""
    day = item.get("day", {}) or {}
    return _safe_int(
        day.get("volume")
        or day.get("v")
        or item.get("volume")
        or item.get("day_volume")
        or item.get("total_volume")
    )


def _snapshot_open_interest(item: dict[str, Any]) -> int:
    """Return open interest across common snapshot/provider field aliases."""
    details = item.get("details", {}) or {}
    return _safe_int(
        item.get("open_interest")
        or item.get("openInterest")
        or item.get("oi")
        or details.get("open_interest")
        or details.get("openInterest")
        or details.get("oi")
    )


def _timestamp_to_datetime(value: Any) -> Optional[datetime]:
    ts = _safe_float(value)
    if ts <= 0:
        return None
    if ts > 1_000_000_000_000_000:
        ts = ts / 1_000_000_000
    elif ts > 1_000_000_000_000:
        ts = ts / 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _snapshot_timestamp(item: dict[str, Any]) -> Optional[datetime]:
    candidates: list[Any] = []
    for section_name in ("last_quote", "last_trade", "day"):
        section = item.get(section_name, {}) or {}
        if isinstance(section, dict):
            candidates.extend(
                section.get(key)
                for key in (
                    "sip_timestamp",
                    "participant_timestamp",
                    "trf_timestamp",
                    "timestamp",
                    "t",
                    "last_updated",
                    "updated",
                )
            )
    candidates.extend(
        item.get(key)
        for key in ("timestamp", "last_updated", "updated", "sip_timestamp")
    )
    timestamps = [dt_value for dt_value in (_timestamp_to_datetime(x) for x in candidates) if dt_value]
    return max(timestamps) if timestamps else None


def _is_snapshot_stale(item: dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    snapshot_time = _snapshot_timestamp(item)
    if snapshot_time is None:
        return False
    now = now or datetime.now(timezone.utc)
    age_sec = (now - snapshot_time).total_seconds()
    return age_sec > OPTIONS_MAX_SNAPSHOT_AGE_SEC


def _contract_notional(item: dict[str, Any]) -> float:
    day = item.get("day", {}) or {}
    volume = _snapshot_volume(item)
    mid = _mid_from_snapshot(item) or _safe_float(day.get("vwap"))
    return volume * mid * 100 if mid else 0.0


def _is_exceptional_volume(volume: int) -> bool:
    """Return True when same-day contract volume is high enough to override stale OI/short-DTE filters."""
    return volume >= max(MIN_OPTION_VOLUME, HIGH_VOLUME_OPTION_MIN_VOLUME)


def _passes_dte_filter(
    dte: int,
    volume: int,
    *,
    min_dte: Optional[int] = None,
    max_dte: Optional[int] = None,
) -> bool:
    lower_bound = MIN_DTE if min_dte is None else min_dte
    upper_bound = MAX_DTE if max_dte is None else max_dte
    if lower_bound <= dte <= upper_bound:
        return True
    exceptional_min_dte = HIGH_VOLUME_OPTION_MIN_DTE if min_dte is None else lower_bound
    return _is_exceptional_volume(volume) and exceptional_min_dte <= dte <= upper_bound


def _passes_volume_filter(volume: int) -> bool:
    if volume >= MIN_OPTION_VOLUME:
        return True
    return not REQUIRE_OPTION_LIQUIDITY_FIELDS and volume <= 0


def _passes_oi_filter(volume: int, oi: int) -> bool:
    if oi >= MIN_OPTION_OI or _is_exceptional_volume(volume):
        return True
    return not REQUIRE_OPTION_LIQUIDITY_FIELDS and oi <= 0


def _option_recommendation_reason(oi: int, volume: int, volume_oi_ratio: float, distance_pct: float, dte: int) -> str:
    qualifiers = []
    if _is_exceptional_volume(volume) and oi <= MIN_OPTION_OI:
        qualifiers.append("exceptional same-day volume overrode stale/low OI")
    if _is_exceptional_volume(volume) and dte < MIN_DTE:
        qualifiers.append("exceptional same-day volume allowed near-term expiry")
    qualifier_text = f" ({'; '.join(qualifiers)})" if qualifiers else ""
    return (
        "Recommended by high-volume/high-OI option-chain liquidity"
        f"{qualifier_text}: OI {oi:,}, volume {volume:,}, "
        f"volume/OI {volume_oi_ratio:.2f}, {distance_pct * 100:.1f}% from spot."
    )


def _expiry_within(details: dict[str, Any], max_days: int) -> bool:
    exp = _expiration_date(details)
    if not exp:
        return False
    try:
        dte = (datetime.fromisoformat(exp).date() - datetime.now(timezone.utc).date()).days
    except ValueError:
        return False
    return 0 <= dte <= max_days


class OptionsApiClient:
    """Small Polygon/Massive-compatible REST client for options flow analytics."""

    def __init__(self, api_key: Optional[str] = OPTIONS_API_KEY, base_url: str = OPTIONS_API_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("OPTIONS_API_KEY, MASSIVE_API_KEY, or POLYGON_API_KEY not set")

        query = dict(params or {})
        query.setdefault("apiKey", self.api_key)
        response = requests.get(f"{self.base_url}{path}", params=query, timeout=15)
        response.raise_for_status()
        return response.json()

    def option_snapshots(self, underlying: str, **params: Any) -> list[dict[str, Any]]:
        payload = self.get(f"/v3/snapshot/options/{underlying}", params=params)
        return payload.get("results", []) or []

    def option_trades(self, option_ticker: str, **params: Any) -> list[dict[str, Any]]:
        payload = self.get(f"/v3/trades/{option_ticker}", params=params)
        return payload.get("results", []) or []


def _empty_flow_report(symbol: str, status: str, reason: str) -> OptionsFlowReport:
    return OptionsFlowReport(
        underlying=symbol,
        status=status,
        score=0,
        bias="NEUTRAL",
        call_premium=0.0,
        put_premium=0.0,
        call_volume=0,
        put_volume=0,
        call_open_interest=0,
        put_open_interest=0,
        net_delta=0.0,
        net_gamma=0.0,
        avg_iv=None,
        iv_rank_proxy=None,
        max_pain_proxy=None,
        put_wall_strike=None,
        call_wall_strike=None,
        dealer_gamma_state="UNKNOWN",
        gamma_squeeze=False,
        signals=[],
        reason=reason,
    )


def _fetch_flow_chain(symbol: str, client: OptionsApiClient) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    for contract_type in ("call", "put"):
        try:
            chain.extend(
                client.option_snapshots(
                    symbol,
                    contract_type=contract_type,
                    limit=250,
                )
            )
        except Exception:
            continue
    return [item for item in chain if _expiry_within(item.get("details", {}) or {}, FLOW_EXPIRY_DAYS)]


def _estimate_trade_notional(trade: dict[str, Any]) -> float:
    price = _safe_float(trade.get("price") or trade.get("p"))
    size = _safe_int(trade.get("size") or trade.get("s"))
    return price * size * 100


def _trade_timestamp(trade: dict[str, Any]) -> int:
    return _safe_int(trade.get("sip_timestamp") or trade.get("participant_timestamp") or trade.get("t"))


def _detect_aggressive_sweeps(
    symbol: str,
    chain: list[dict[str, Any]],
    client: OptionsApiClient,
) -> list[OptionsFlowSignal]:
    """Flag large same-contract prints as sweep/block proxies from Polygon trades."""
    signals: list[OptionsFlowSignal] = []
    liquid = sorted(chain, key=_contract_notional, reverse=True)[:FLOW_TOP_CONTRACTS]

    for item in liquid:
        details = item.get("details", {}) or {}
        ticker = _option_ticker(details)
        contract_type = _option_type(details)
        if not ticker or contract_type not in {"call", "put"}:
            continue

        try:
            trades = client.option_trades(ticker, limit=FLOW_TRADE_LIMIT, order="desc", sort="timestamp")
        except Exception:
            continue

        large_prints = [t for t in trades if _estimate_trade_notional(t) >= SWEEP_NOTIONAL_THRESHOLD]
        if not large_prints:
            continue

        total_notional = sum(_estimate_trade_notional(t) for t in large_prints)
        unique_timestamps = len({_trade_timestamp(t) for t in large_prints})
        name = "aggressive_call_sweeps" if contract_type == "call" else "aggressive_put_sweeps"
        direction = "BULLISH" if contract_type == "call" else "BEARISH"
        severity = min(30, int(total_notional / SWEEP_NOTIONAL_THRESHOLD) * 5 + len(large_prints) * 3)
        block_text = "block/sweep" if total_notional >= BLOCK_NOTIONAL_THRESHOLD else "sweep"
        signals.append(
            OptionsFlowSignal(
                name=name,
                direction=direction,
                severity=max(10, severity),
                description=f"Detected {len(large_prints)} large {contract_type} {block_text} prints on {ticker}.",
                evidence={
                    "contract": ticker,
                    "prints": len(large_prints),
                    "notional": round(total_notional, 2),
                    "unique_timestamps": unique_timestamps,
                },
            )
        )

    return signals[:6]


def analyze_options_flow(
    symbol: str,
    direction: Optional[str] = None,
    client: Optional[OptionsApiClient] = None,
) -> OptionsFlowReport:
    """Build a true options flow/liquidity report for intraday or swing setups.

    Uses Polygon/Massive-compatible options snapshots for IV, greeks, volume and OI,
    and recent option trades for large-print sweep/block proxies. Historical OI is
    not available in the real-time snapshot, so OI build is approximated with
    volume/open-interest pressure and highlighted as a proxy.
    """
    api = client or OptionsApiClient()
    if not api.configured:
        return _empty_flow_report(symbol, "SKIP", "Options API key not set")

    try:
        chain = _fetch_flow_chain(symbol, api)
    except Exception as exc:
        return _empty_flow_report(symbol, "ERROR", f"Options flow fetch failed: {exc}")

    if not chain:
        return _empty_flow_report(symbol, "SKIP", "No option chain snapshots returned")

    signals: list[OptionsFlowSignal] = []
    call_premium = put_premium = 0.0
    call_volume = put_volume = 0
    call_oi = put_oi = 0
    call_delta = put_delta = 0.0
    call_gamma = put_gamma = 0.0
    iv_values: list[float] = []
    weighted_strikes: list[tuple[float, int]] = []
    put_walls: dict[float, int] = {}
    call_walls: dict[float, int] = {}

    for item in chain:
        details = item.get("details", {}) or {}
        contract_type = _option_type(details)
        strike = _strike(details)
        greeks = item.get("greeks", {}) or {}

        volume = _snapshot_volume(item)
        oi = _snapshot_open_interest(item)
        mid = _mid_from_snapshot(item)
        notional = volume * (mid or 0.0) * 100
        delta = _safe_float(greeks.get("delta"))
        gamma = _safe_float(greeks.get("gamma"))
        iv = item.get("implied_volatility")

        if iv is not None:
            iv_values.append(_safe_float(iv))
        if strike and oi:
            weighted_strikes.append((strike, oi))

        if contract_type == "call":
            call_premium += notional
            call_volume += volume
            call_oi += oi
            call_delta += abs(delta) * volume * 100
            call_gamma += abs(gamma) * oi * 100
            call_walls[strike] = call_walls.get(strike, 0) + oi
        elif contract_type == "put":
            put_premium += notional
            put_volume += volume
            put_oi += oi
            put_delta += abs(delta) * volume * 100
            put_gamma += abs(gamma) * oi * 100
            put_walls[strike] = put_walls.get(strike, 0) + oi

        if oi and volume / max(oi, 1) >= OI_BUILD_VOLUME_OI_RATIO and volume >= MIN_OPTION_VOLUME:
            dir_name = "BULLISH" if contract_type == "call" else "BEARISH"
            signals.append(
                OptionsFlowSignal(
                    name="oi_build_proxy",
                    direction=dir_name,
                    severity=min(18, int((volume / max(oi, 1)) * 10)),
                    description=f"{contract_type.upper()} volume/OI pressure suggests fresh positioning near {strike}.",
                    evidence={"strike": strike, "volume": volume, "open_interest": oi, "volume_oi_ratio": round(volume / max(oi, 1), 2)},
                )
            )

    put_wall_strike, put_wall_oi = max(put_walls.items(), key=lambda x: x[1], default=(None, 0))
    call_wall_strike, call_wall_oi = max(call_walls.items(), key=lambda x: x[1], default=(None, 0))

    if put_wall_strike is not None and put_wall_oi >= PUT_WALL_OI_THRESHOLD:
        signals.append(
            OptionsFlowSignal(
                name="put_wall",
                direction="SUPPORT",
                severity=min(20, int(put_wall_oi / PUT_WALL_OI_THRESHOLD) * 5 + 8),
                description=f"Large put wall detected at {put_wall_strike}.",
                evidence={"strike": put_wall_strike, "open_interest": put_wall_oi},
            )
        )
    if call_wall_strike is not None and call_wall_oi >= CALL_WALL_OI_THRESHOLD:
        signals.append(
            OptionsFlowSignal(
                name="call_wall",
                direction="RESISTANCE",
                severity=min(20, int(call_wall_oi / CALL_WALL_OI_THRESHOLD) * 5 + 8),
                description=f"Large call wall detected at {call_wall_strike}.",
                evidence={"strike": call_wall_strike, "open_interest": call_wall_oi},
            )
        )

    avg_iv = sum(iv_values) / len(iv_values) if iv_values else None
    iv_rank_proxy = None
    if avg_iv is not None:
        # Snapshot-only proxy: above normal when the chain average exceeds the configured max IV guardrail ratio.
        iv_rank_proxy = avg_iv / max(MAX_IV, 0.01)
        if iv_rank_proxy >= IV_EXPANSION_RATIO / max(1.0, MAX_IV):
            signals.append(
                OptionsFlowSignal(
                    name="iv_expansion",
                    direction="VOLATILITY",
                    severity=min(18, int(iv_rank_proxy * 10)),
                    description="Chain IV is elevated versus configured IV guardrail, confirming volatility expansion risk.",
                    evidence={"avg_iv": round(avg_iv, 4), "iv_rank_proxy": round(iv_rank_proxy, 3)},
                )
            )

    delta_total = call_delta + put_delta
    net_delta = call_delta - put_delta
    delta_ratio = max(call_delta, put_delta) / max(min(call_delta, put_delta), 1)
    if delta_total and delta_ratio >= DELTA_IMBALANCE_RATIO:
        imbalance_direction = "BULLISH" if call_delta > put_delta else "BEARISH"
        signals.append(
            OptionsFlowSignal(
                name="delta_imbalance",
                direction=imbalance_direction,
                severity=min(22, int(delta_ratio * 5)),
                description=f"{imbalance_direction.lower()} delta imbalance detected across active contracts.",
                evidence={"call_delta": round(call_delta, 2), "put_delta": round(put_delta, 2), "ratio": round(delta_ratio, 2)},
            )
        )

    try:
        signals.extend(_detect_aggressive_sweeps(symbol, chain, api))
    except Exception:
        pass

    total_gamma = call_gamma + put_gamma
    net_gamma = call_gamma - put_gamma
    dealer_gamma_state = "LONG_GAMMA" if net_gamma >= 0 else "SHORT_GAMMA"
    bullish_pressure = sum(s.severity for s in signals if s.direction in {"BULLISH", "SUPPORT", "VOLATILITY"})
    bearish_pressure = sum(s.severity for s in signals if s.direction in {"BEARISH", "RESISTANCE", "VOLATILITY"})
    premium_pressure = 0
    if call_premium or put_premium:
        premium_ratio = call_premium / max(put_premium, 1)
        premium_pressure = 12 if premium_ratio >= DELTA_IMBALANCE_RATIO else -12 if (1 / max(premium_ratio, 0.01)) >= DELTA_IMBALANCE_RATIO else 0

    squeeze_raw = bullish_pressure + max(0, premium_pressure) + (10 if dealer_gamma_state == "SHORT_GAMMA" else 0)
    gamma_squeeze = squeeze_raw >= GAMMA_SQUEEZE_MIN_SCORE and call_volume > put_volume and call_delta > put_delta
    if gamma_squeeze:
        signals.append(
            OptionsFlowSignal(
                name="gamma_squeeze_conditions",
                direction="BULLISH",
                severity=25,
                description="Call demand, elevated gamma exposure, and short-gamma dealer state create squeeze conditions.",
                evidence={"squeeze_raw": squeeze_raw, "net_gamma": round(net_gamma, 2), "total_gamma": round(total_gamma, 2)},
            )
        )
        bullish_pressure += 25

    directional_score = bullish_pressure - bearish_pressure + premium_pressure
    if direction == "CALL":
        score = 50 + directional_score
    elif direction == "PUT":
        score = 50 - directional_score
    else:
        score = 50 + abs(directional_score)
    score = int(max(0, min(100, score)))

    if directional_score > 10:
        bias = "BULLISH"
    elif directional_score < -10:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    max_pain_proxy = None
    if weighted_strikes:
        total_oi = sum(oi for _, oi in weighted_strikes)
        max_pain_proxy = sum(strike * oi for strike, oi in weighted_strikes) / max(total_oi, 1)

    reason = (
        f"Options flow bias {bias}; score {score}; call premium ${call_premium:,.0f} vs "
        f"put premium ${put_premium:,.0f}; dealer gamma {dealer_gamma_state}."
    )

    return OptionsFlowReport(
        underlying=symbol,
        status="OK",
        score=score,
        bias=bias,
        call_premium=round(call_premium, 2),
        put_premium=round(put_premium, 2),
        call_volume=call_volume,
        put_volume=put_volume,
        call_open_interest=call_oi,
        put_open_interest=put_oi,
        net_delta=round(net_delta, 2),
        net_gamma=round(net_gamma, 2),
        avg_iv=_round_or_none(avg_iv, 4),
        iv_rank_proxy=_round_or_none(iv_rank_proxy, 3),
        max_pain_proxy=_round_or_none(max_pain_proxy, 2),
        put_wall_strike=put_wall_strike,
        call_wall_strike=call_wall_strike,
        dealer_gamma_state=dealer_gamma_state,
        gamma_squeeze=gamma_squeeze,
        signals=sorted(signals, key=lambda s: s.severity, reverse=True)[:12],
        reason=reason,
    )


def options_flow_to_dict(report: OptionsFlowReport) -> dict[str, Any]:
    data = asdict(report)
    data["signals"] = [asdict(signal) for signal in report.signals]
    return data


def format_options_flow(report: OptionsFlowReport) -> str:
    if report.status != "OK":
        return f"🧨 Options Flow: {report.status} - {report.reason}"

    top_signals = ", ".join(signal.name for signal in report.signals[:4]) or "none"
    return (
        f"🧨 *Options Flow:* {report.bias} {report.score}/100 | Gamma: {report.dealer_gamma_state} | "
        f"Squeeze: {report.gamma_squeeze}\n"
        f"💵 *Premium:* Calls ${report.call_premium:,.0f} / Puts ${report.put_premium:,.0f} | "
        f"Δ Net {report.net_delta:,.0f}\n"
        f"🧱 *Walls:* Put {report.put_wall_strike or 'n/a'} / Call {report.call_wall_strike or 'n/a'} | "
        f"IV {report.avg_iv if report.avg_iv is not None else 'n/a'} | MaxPain≈{report.max_pain_proxy or 'n/a'}\n"
        f"🔎 *Signals:* {top_signals}"
    )


def _empty_option_candidate(symbol: str, option_type: str, status: str, reason: str) -> OptionCandidate:
    return OptionCandidate(
        underlying=symbol,
        contract_symbol="",
        option_type=option_type.upper() if option_type else "",
        strike=0,
        expiry="",
        dte=0,
        bid=None,
        ask=None,
        mid=None,
        spread_pct=None,
        delta=None,
        gamma=None,
        theta=None,
        implied_volatility=None,
        volume=None,
        open_interest=None,
        status=status,
        reason=reason,
    )


def _log_score(value: int, cap: float, scale: float = 5.0) -> float:
    if value <= 0:
        return 0.0
    return min(cap, math.log10(value + 1) * scale)


def _score_option_candidate(
    *,
    strike: float,
    price: float,
    volume: int,
    oi: int,
    spread: Optional[float],
    delta: Optional[float],
    iv: Optional[float],
    mid: Optional[float],
) -> tuple[float, float, float, float]:
    """Score a contract with a heavy OI/volume bias for actionable liquidity."""
    distance_pct = abs(strike - price) / price if price else 1.0
    atm_score = max(0.0, 22.0 * (1.0 - min(distance_pct, 0.12) / 0.12))

    volume_score = _log_score(volume, 28.0, 6.0)
    oi_score = _log_score(oi, 24.0, 5.5)
    volume_oi_ratio = volume / max(oi, 1)
    participation_score = min(16.0, volume_oi_ratio * 28.0)
    liquidity_score = volume_score + oi_score + participation_score

    spread_score = 8.0
    if spread is not None:
        spread_score = max(0.0, 12.0 * (1.0 - min(spread, MAX_SPREAD_PCT) / max(MAX_SPREAD_PCT, 0.01)))

    delta_score = 6.0
    if delta is not None:
        target_mid = (TARGET_MIN_DELTA + TARGET_MAX_DELTA) / 2
        delta_score = max(0.0, 10.0 * (1.0 - abs(abs(delta) - target_mid) / max(target_mid, 0.01)))

    iv_score = 5.0
    if iv is not None:
        iv_score = max(0.0, 8.0 * (1.0 - min(iv, MAX_IV) / max(MAX_IV, 0.01)))

    premium_score = 0.0
    if mid:
        premium_score = max(0.0, min(4.0, 4.0 - (mid / max(price, 1.0)) * 25.0))

    total_score = atm_score + liquidity_score + spread_score + delta_score + iv_score + premium_score
    return total_score, liquidity_score, volume_oi_ratio, distance_pct


def _candidate_from_chain_item(
    symbol: str,
    option_type: str,
    item: dict[str, Any],
    price: float,
    fallback_expiry: str = "",
) -> tuple[Optional[OptionCandidate], Optional[str]]:
    details = item.get("details", {}) or {}
    strike = _strike(details)
    contract = _option_ticker(details)
    exp = _expiration_date(details) or fallback_expiry
    contract_type = _option_type(details) or option_type
    if not contract or not strike:
        return None, "missing_contract"
    if contract_type and contract_type != option_type:
        return None, "side"

    try:
        dte = (datetime.fromisoformat(exp).date() - datetime.now(timezone.utc).date()).days
    except ValueError:
        return None, "dte"

    bid_float, ask_float, quote_midpoint = _quote_prices(item)
    mid = quote_midpoint or _mid_from_snapshot(item)
    spread = _spread_pct(bid_float, ask_float)

    greeks = item.get("greeks", {}) or {}
    delta = greeks.get("delta")
    gamma = greeks.get("gamma")
    theta = greeks.get("theta")
    iv = item.get("implied_volatility")

    volume = _snapshot_volume(item)
    oi = _snapshot_open_interest(item)

    if _is_snapshot_stale(item):
        return None, "stale"
    if not _passes_dte_filter(dte, volume):
        return None, "dte"
    if spread is not None and spread > MAX_SPREAD_PCT:
        return None, "spread"
    if _contract_entry_price(bid_float, ask_float, mid) < MIN_OPTION_PREMIUM:
        return None, "premium"
    if not _passes_volume_filter(volume):
        return None, "volume"
    if not _passes_oi_filter(volume, oi):
        return None, "oi"
    if iv is not None and _safe_float(iv) > MAX_IV:
        return None, "iv"
    # Delta is a quality input, not a hard liquidity filter.  Keep high-volume/high-OI
    # contracts eligible so alerts do not recommend a thinner contract solely because
    # the liquid contract is slightly outside the target delta band.
    score, liquidity_score, volume_oi_ratio, distance_pct = _score_option_candidate(
        strike=strike,
        price=price,
        volume=volume,
        oi=oi,
        spread=spread,
        delta=_safe_float(delta) if delta is not None else None,
        iv=_safe_float(iv) if iv is not None else None,
        mid=mid,
    )

    dollar_volume = volume * (mid or 0.0) * 100
    candidate = OptionCandidate(
        underlying=symbol,
        contract_symbol=contract,
        option_type=option_type.upper(),
        strike=strike,
        expiry=exp,
        dte=dte,
        bid=bid_float,
        ask=ask_float,
        mid=round(mid, 2) if mid else None,
        spread_pct=round(spread, 2) if spread is not None else None,
        delta=round(_safe_float(delta), 3) if delta is not None else None,
        gamma=round(_safe_float(gamma), 4) if gamma is not None else None,
        theta=round(_safe_float(theta), 4) if theta is not None else None,
        implied_volatility=round(_safe_float(iv), 3) if iv is not None else None,
        volume=volume,
        open_interest=oi,
        status="OK",
        reason=_option_recommendation_reason(oi, volume, volume_oi_ratio, distance_pct, dte),
        recommendation_score=round(score, 2),
        liquidity_score=round(liquidity_score, 2),
        volume_oi_ratio=round(volume_oi_ratio, 3),
        dollar_volume=round(dollar_volume, 2),
    )
    return candidate, None



def _default_otm_candidate_from_chain_item(
    symbol: str,
    option_type: str,
    item: dict[str, Any],
    price: float,
    fallback_expiry: str = "",
    fallback_label: str = "same-week",
) -> Optional[OptionCandidate]:
    """Build a 5% OTM fallback candidate without strict liquidity filters."""
    details = item.get("details", {}) or {}
    strike = _strike(details)
    contract = _option_ticker(details)
    exp = _expiration_date(details) or fallback_expiry
    contract_type = _option_type(details) or option_type
    if not contract or not strike or not exp:
        return None
    if contract_type and contract_type != option_type:
        return None

    try:
        dte = (datetime.fromisoformat(exp).date() - datetime.now(timezone.utc).date()).days
    except ValueError:
        return None

    bid_float, ask_float, quote_midpoint = _quote_prices(item)
    mid = quote_midpoint or _mid_from_snapshot(item)
    spread = _spread_pct(bid_float, ask_float)
    greeks = item.get("greeks", {}) or {}
    delta = greeks.get("delta")
    gamma = greeks.get("gamma")
    theta = greeks.get("theta")
    iv = item.get("implied_volatility")
    volume = _snapshot_volume(item)
    oi = _snapshot_open_interest(item)
    dollar_volume = volume * (mid or 0.0) * 100
    if _is_snapshot_stale(item):
        return None
    if _contract_entry_price(bid_float, ask_float, mid) < MIN_OPTION_PREMIUM:
        return None

    option_label = "CALL" if option_type == "call" else "PUT"
    pct_label = "+5%" if option_type == "call" else "-5%"
    return OptionCandidate(
        underlying=symbol,
        contract_symbol=contract,
        option_type=option_label,
        strike=strike,
        expiry=exp,
        dte=dte,
        bid=bid_float,
        ask=ask_float,
        mid=round(mid, 2) if mid else None,
        spread_pct=round(spread, 2) if spread is not None else None,
        delta=round(_safe_float(delta), 3) if delta is not None else None,
        gamma=round(_safe_float(gamma), 4) if gamma is not None else None,
        theta=round(_safe_float(theta), 4) if theta is not None else None,
        implied_volatility=round(_safe_float(iv), 3) if iv is not None else None,
        volume=volume,
        open_interest=oi,
        status="OK",
        reason=f"Default fallback after SKIP: buy {fallback_label} {pct_label} OTM {option_label} contract",
        recommendation_score=0.0,
        liquidity_score=0.0,
        volume_oi_ratio=round(volume / max(oi, 1), 3) if oi is not None else None,
        dollar_volume=round(dollar_volume, 2),
    )


def _valid_data_candidate_from_chain_item(
    symbol: str,
    option_type: str,
    item: dict[str, Any],
    price: float,
    fallback_expiry: str = "",
    fallback_reason: str = "Best available contract after strict filters skipped",
) -> Optional[OptionCandidate]:
    """Build a fallback candidate when a snapshot has enough data for an alert/order."""
    details = item.get("details", {}) or {}
    strike = _strike(details)
    contract = _option_ticker(details)
    exp = _expiration_date(details) or fallback_expiry
    contract_type = _option_type(details) or option_type
    if not contract or not strike or not exp:
        return None
    if contract_type and contract_type != option_type:
        return None

    try:
        dte = (datetime.fromisoformat(exp).date() - datetime.now(timezone.utc).date()).days
    except ValueError:
        return None
    if dte < 0:
        return None

    bid_float, ask_float, quote_midpoint = _quote_prices(item)
    mid = quote_midpoint or _mid_from_snapshot(item)
    spread = _spread_pct(bid_float, ask_float)
    snapshot_is_stale = _is_snapshot_stale(item)
    if _contract_entry_price(bid_float, ask_float, mid) <= 0:
        return None

    greeks = item.get("greeks", {}) or {}
    delta = greeks.get("delta")
    gamma = greeks.get("gamma")
    theta = greeks.get("theta")
    iv = item.get("implied_volatility")
    volume = _snapshot_volume(item)
    oi = _snapshot_open_interest(item)
    score, liquidity_score, volume_oi_ratio, distance_pct = _score_option_candidate(
        strike=strike,
        price=price,
        volume=volume,
        oi=oi,
        spread=spread,
        delta=_safe_float(delta) if delta is not None else None,
        iv=_safe_float(iv) if iv is not None else None,
        mid=mid,
    )
    dollar_volume = volume * (mid or 0.0) * 100
    option_label = "CALL" if option_type == "call" else "PUT"
    stale_warning = (
        " Snapshot timestamp is stale, so treat pricing as a fallback limit reference."
        if snapshot_is_stale
        else ""
    )
    return OptionCandidate(
        underlying=symbol,
        contract_symbol=contract,
        option_type=option_label,
        strike=strike,
        expiry=exp,
        dte=dte,
        bid=bid_float,
        ask=ask_float,
        mid=round(mid, 2) if mid else None,
        spread_pct=round(spread, 2) if spread is not None else None,
        delta=round(_safe_float(delta), 3) if delta is not None else None,
        gamma=round(_safe_float(gamma), 4) if gamma is not None else None,
        theta=round(_safe_float(theta), 4) if theta is not None else None,
        implied_volatility=round(_safe_float(iv), 3) if iv is not None else None,
        volume=volume,
        open_interest=oi,
        status="OK",
        reason=(
            f"{fallback_reason}: using valid {option_label} snapshot with positive pricing; "
            f"strict liquidity/quality filters were not all met.{stale_warning} "
            f"OI {oi:,}, volume {volume:,}, "
            f"volume/OI {volume_oi_ratio:.2f}, {distance_pct * 100:.1f}% from spot."
        ),
        recommendation_score=round(score, 2),
        liquidity_score=round(liquidity_score, 2),
        volume_oi_ratio=round(volume_oi_ratio, 3),
        dollar_volume=round(dollar_volume, 2),
    )


def _select_default_otm_candidate(
    symbol: str,
    option_type: str,
    price: float,
    api: OptionsApiClient,
    *,
    min_dte: int = 0,
    max_dte: int = 6,
) -> Optional[OptionCandidate]:
    """Select the nearest +5% call or -5% put contract for SKIP fallbacks."""
    if price <= 0 or option_type not in {"call", "put"}:
        return None

    expiries = _next_fridays(min_dte=min_dte, max_dte=max_dte)
    if not expiries:
        return None

    target_strike = price * (1.05 if option_type == "call" else 0.95)
    candidates: list[OptionCandidate] = []
    fallback_label = "same-week" if min_dte <= 0 else f"{min_dte}-{max_dte} DTE"

    for expiry in expiries:
        try:
            results = api.option_snapshots(
                symbol,
                expiration_date=expiry,
                contract_type=option_type,
                limit=250,
            )
        except Exception:
            continue

        for item in results:
            candidate = _default_otm_candidate_from_chain_item(
                symbol,
                option_type,
                item,
                price,
                fallback_expiry=expiry,
                fallback_label=fallback_label,
            )
            if candidate:
                candidates.append(candidate)

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda candidate: (
            abs(candidate.strike - target_strike),
            candidate.dte,
            -float(candidate.volume or 0),
            -float(candidate.open_interest or 0),
        ),
    )


def _select_best_available_candidate(
    symbol: str,
    option_type: str,
    price: float,
    api: OptionsApiClient,
    *,
    min_dte: int = 0,
    max_dte: int = MAX_DTE,
) -> Optional[OptionCandidate]:
    """Select any valid same-side snapshot with positive pricing as a final fallback."""
    if price <= 0 or option_type not in {"call", "put"}:
        return None

    expiries = _next_fridays(min_dte=min(0, min_dte), max_dte=max_dte)
    candidates: list[OptionCandidate] = []
    target_strike = price * (1.05 if option_type == "call" else 0.95)

    for expiry in expiries:
        try:
            results = api.option_snapshots(
                symbol,
                expiration_date=expiry,
                contract_type=option_type,
                limit=250,
            )
        except Exception:
            continue

        for item in results:
            candidate = _valid_data_candidate_from_chain_item(
                symbol,
                option_type,
                item,
                price,
                fallback_expiry=expiry,
            )
            if candidate:
                candidates.append(candidate)

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda candidate: (
            candidate.dollar_volume or 0.0,
            candidate.volume or 0,
            candidate.open_interest or 0,
            -(abs(candidate.strike - target_strike)),
            -(candidate.spread_pct or MAX_SPREAD_PCT),
            -candidate.dte,
        ),
    )


def _select_same_week_default_candidate(
    symbol: str,
    option_type: str,
    price: float,
    api: OptionsApiClient,
) -> Optional[OptionCandidate]:
    """Backward-compatible same-week default fallback selector."""
    return _select_default_otm_candidate(symbol, option_type, price, api, min_dte=0, max_dte=6)

def _option_candidate_rank(candidate: OptionCandidate) -> tuple[float, ...]:
    """Rank candidates by raw volume and OI first, then quality tie-breakers.

    The alert should not choose a thinner contract when another eligible contract
    has better same-day participation. Same-day volume is the first sort key, OI
    is the second, and score/spread are only tie-breakers so ATM/delta quality
    cannot make a lower-volume contract win ahead of a more active strike.
    """
    volume = candidate.volume or 0
    oi = candidate.open_interest or 0
    raw_liquidity = volume * oi
    return (
        volume,
        oi,
        raw_liquidity,
        candidate.dollar_volume or 0.0,
        candidate.liquidity_score or 0.0,
        candidate.recommendation_score or 0.0,
        -(candidate.spread_pct or MAX_SPREAD_PCT),
    )


def recommend_option_contracts_from_chain(
    symbol: str,
    option_chain: list[dict[str, Any]],
    analysis: dict,
    *,
    top_n: int = 3,
) -> list[OptionCandidate]:
    """Rank option-chain snapshots by high volume, OI, and tradable liquidity.

    This helper is useful when an option chain has already been fetched by another
    provider or test fixture. It applies the same spread, IV, DTE, high-volume,
    and high-OI guardrails as the live selector, treats delta as a quality score
    rather than a hard rejection, then returns only the highest-liquidity
    contracts.
    """
    option_type = _option_side_from_signal(analysis.get("signal", "") or analysis.get("direction", ""))
    price = _safe_float(analysis.get("price"))
    if not option_type or price <= 0 or top_n <= 0:
        return []

    candidates: list[OptionCandidate] = []
    for item in option_chain:
        candidate, _ = _candidate_from_chain_item(symbol, option_type, item, price)
        if candidate:
            candidates.append(candidate)

    candidates.sort(key=_option_candidate_rank, reverse=True)
    return candidates[:top_n]


def select_option_contract(
    symbol: str,
    analysis: dict,
    client: Optional[OptionsApiClient] = None,
    *,
    min_dte: Optional[int] = None,
    max_dte: Optional[int] = None,
    allow_default_fallback: bool = True,
) -> OptionCandidate:
    """Recommend the best directional option contract using Polygon/Massive snapshots.

    The selector enforces spread, IV, minimum premium, DTE, high-volume, and high-OI guardrails
    while treating delta as a quality score. Ranking prioritizes same-day option
    volume first and open interest second so alerts only recommend contracts
    traders can realistically enter and exit.
    """
    option_type = _option_side_from_signal(analysis.get("signal", "") or analysis.get("direction", ""))
    if not option_type:
        return _empty_option_candidate(symbol, "", "SKIP", "No directional option side")

    api = client or OptionsApiClient()
    if not api.configured:
        return _empty_option_candidate(symbol, option_type, "SKIP", "OPTIONS_API_KEY, MASSIVE_API_KEY, or POLYGON_API_KEY not set")

    price = _safe_float(analysis.get("price"))
    if price <= 0:
        return _empty_option_candidate(symbol, option_type, "SKIP", "Underlying price missing for option recommendation")

    effective_min_dte = min_dte if min_dte is not None else min(MIN_DTE, HIGH_VOLUME_OPTION_MIN_DTE)
    effective_max_dte = max_dte if max_dte is not None else MAX_DTE
    expiries = _next_fridays(min_dte=effective_min_dte, max_dte=effective_max_dte)
    best: Optional[OptionCandidate] = None
    best_rank: tuple[float, ...] = (-1.0,)
    rejection_counts = {"premium": 0, "spread": 0, "volume": 0, "oi": 0, "iv": 0, "dte": 0, "stale": 0}

    for expiry in expiries:
        try:
            results = api.option_snapshots(
                symbol,
                expiration_date=expiry,
                contract_type=option_type,
                limit=250,
            )
        except Exception:
            continue

        for item in results:
            details = item.get("details", {}) or {}
            strike = _strike(details)
            contract = _option_ticker(details)
            exp = _expiration_date(details) or expiry
            if not contract or not strike:
                continue

            try:
                dte = (datetime.fromisoformat(exp).date() - datetime.now(timezone.utc).date()).days
            except ValueError:
                dte = (datetime.fromisoformat(expiry).date() - datetime.now(timezone.utc).date()).days

            bid_float, ask_float, quote_midpoint = _quote_prices(item)
            mid = quote_midpoint or _mid_from_snapshot(item)
            spread = _spread_pct(bid_float, ask_float)

            greeks = item.get("greeks", {}) or {}
            delta = greeks.get("delta")
            gamma = greeks.get("gamma")
            theta = greeks.get("theta")
            iv = item.get("implied_volatility")

            volume = _snapshot_volume(item)
            oi = _snapshot_open_interest(item)

            if _is_snapshot_stale(item):
                rejection_counts["stale"] += 1
                continue
            if not _passes_dte_filter(dte, volume, min_dte=effective_min_dte, max_dte=effective_max_dte):
                rejection_counts["dte"] += 1
                continue
            if spread is not None and spread > MAX_SPREAD_PCT:
                rejection_counts["spread"] += 1
                continue
            if _contract_entry_price(bid_float, ask_float, mid) < MIN_OPTION_PREMIUM:
                rejection_counts["premium"] += 1
                continue
            if not _passes_volume_filter(volume):
                rejection_counts["volume"] += 1
                continue
            if not _passes_oi_filter(volume, oi):
                rejection_counts["oi"] += 1
                continue
            if iv is not None and _safe_float(iv) > MAX_IV:
                rejection_counts["iv"] += 1
                continue
            # Delta is scored below, but it should not hide the most liquid contract.
            # Traders complained when lower volume/OI contracts won only because the
            # higher-liquidity strike sat outside the preferred delta band.
            score, liquidity_score, volume_oi_ratio, distance_pct = _score_option_candidate(
                strike=strike,
                price=price,
                volume=volume,
                oi=oi,
                spread=spread,
                delta=_safe_float(delta) if delta is not None else None,
                iv=_safe_float(iv) if iv is not None else None,
                mid=mid,
            )

            dollar_volume = volume * (mid or 0.0) * 100
            candidate = OptionCandidate(
                underlying=symbol,
                contract_symbol=contract,
                option_type=option_type.upper(),
                strike=strike,
                expiry=exp,
                dte=dte,
                bid=bid_float,
                ask=ask_float,
                mid=round(mid, 2) if mid else None,
                spread_pct=round(spread, 2) if spread is not None else None,
                delta=round(_safe_float(delta), 3) if delta is not None else None,
                gamma=round(_safe_float(gamma), 4) if gamma is not None else None,
                theta=round(_safe_float(theta), 4) if theta is not None else None,
                implied_volatility=round(_safe_float(iv), 3) if iv is not None else None,
                volume=volume,
                open_interest=oi,
                status="OK",
                reason=_option_recommendation_reason(oi, volume, volume_oi_ratio, distance_pct, dte),
                recommendation_score=round(score, 2),
                liquidity_score=round(liquidity_score, 2),
                volume_oi_ratio=round(volume_oi_ratio, 3),
                dollar_volume=round(dollar_volume, 2),
            )
            rank = _option_candidate_rank(candidate)
            if rank > best_rank:
                best_rank = rank
                best = candidate

    if best:
        return best

    if allow_default_fallback:
        default_candidate = _select_default_otm_candidate(
            symbol,
            option_type,
            price,
            api,
            min_dte=effective_min_dte,
            max_dte=effective_max_dte,
        )
        if default_candidate:
            return default_candidate

        best_available_candidate = _select_best_available_candidate(
            symbol,
            option_type,
            price,
            api,
            min_dte=effective_min_dte,
            max_dte=effective_max_dte,
        )
        if best_available_candidate:
            return best_available_candidate

    rejection_text = ", ".join(f"{name}={count}" for name, count in rejection_counts.items() if count)
    suffix = f" ({rejection_text})" if rejection_text else ""
    return _empty_option_candidate(
        symbol,
        option_type,
        "SKIP",
        f"No option passed high-volume/high-OI, minimum premium, spread, DTE, and IV filters{suffix}; configured 5% OTM fallback unavailable",
    )


def option_to_dict(candidate: OptionCandidate) -> dict:
    return asdict(candidate)


def estimate_option_pnl(entry_premium: float, exit_premium: float, contracts: int = 1) -> dict:
    multiplier = 100
    pnl = (exit_premium - entry_premium) * contracts * multiplier
    return {
        "entry_premium": entry_premium,
        "exit_premium": exit_premium,
        "contracts": contracts,
        "pnl_dollars": round(pnl, 2),
        "pnl_pct": round(((exit_premium - entry_premium) / entry_premium) * 100, 2) if entry_premium else 0,
    }


def format_option_alert(candidate: OptionCandidate) -> str:
    if candidate.status != "OK":
        return f"Options: SKIP - {candidate.reason}"
    return (
        f"Options: {candidate.contract_symbol}\n"
        f"Type: {candidate.option_type} | Strike: {candidate.strike} | Exp: {candidate.expiry} ({candidate.dte} DTE)\n"
        f"Bid/Ask/Mid: {candidate.bid}/{candidate.ask}/{candidate.mid} | Spread: {candidate.spread_pct}%\n"
        f"Delta: {candidate.delta} | IV: {candidate.implied_volatility} | "
        f"Vol/OI: {candidate.volume}/{candidate.open_interest} ({candidate.volume_oi_ratio}) | "
        f"Score: {candidate.recommendation_score}"
    )
