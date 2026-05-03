from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional

import requests

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

MIN_OPTION_VOLUME = int(os.getenv("MIN_OPTION_VOLUME", "100"))
MIN_OPTION_OI = int(os.getenv("MIN_OPTION_OI", "250"))
MAX_SPREAD_PCT = float(os.getenv("MAX_OPTION_SPREAD_PCT", "12"))
MAX_IV = float(os.getenv("MAX_OPTION_IV", "1.20"))
TARGET_MIN_DELTA = float(os.getenv("TARGET_MIN_DELTA", "0.35"))
TARGET_MAX_DELTA = float(os.getenv("TARGET_MAX_DELTA", "0.65"))
MIN_DTE = int(os.getenv("MIN_OPTION_DTE", "7"))
MAX_DTE = int(os.getenv("MAX_OPTION_DTE", "21"))


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


def _next_fridays(min_dte: int = MIN_DTE, max_dte: int = MAX_DTE) -> list[str]:
    today = datetime.utcnow().date()
    dates = []
    for i in range(min_dte, max_dte + 1):
        d = today + timedelta(days=i)
        if d.weekday() == 4:
            dates.append(d.isoformat())
    return dates or [(today + timedelta(days=min_dte)).isoformat()]


def _option_side_from_signal(signal: str) -> Optional[str]:
    if "BULLISH" in signal or "UPTREND" in signal:
        return "call"
    if "BEARISH" in signal or "DOWNTREND" in signal:
        return "put"
    return None


def _spread_pct(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid is None or ask is None or ask <= 0:
        return None
    mid = (bid + ask) / 2
    if mid <= 0:
        return None
    return ((ask - bid) / mid) * 100


def select_option_contract(symbol: str, analysis: dict) -> OptionCandidate:
    """Pick a liquid near-ATM option contract using Polygon snapshot data."""
    option_type = _option_side_from_signal(analysis.get("signal", ""))
    if not option_type:
        return OptionCandidate(symbol, "", "", 0, "", 0, None, None, None, None, None, None, None, None, None, None, "SKIP", "No directional option side")

    if not POLYGON_API_KEY:
        return OptionCandidate(symbol, "", option_type.upper(), 0, "", 0, None, None, None, None, None, None, None, None, None, None, "SKIP", "POLYGON_API_KEY not set")

    price = float(analysis.get("price", 0))
    expiries = _next_fridays()
    best = None
    best_score = -10**9

    for expiry in expiries:
        url = f"https://api.polygon.io/v3/snapshot/options/{symbol}"
        params = {
            "apiKey": POLYGON_API_KEY,
            "expiration_date": expiry,
            "contract_type": option_type,
            "limit": 250,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception:
            continue

        for item in results:
            details = item.get("details", {})
            strike = float(details.get("strike_price") or 0)
            contract = details.get("ticker", "")
            exp = details.get("expiration_date", expiry)
            dte = (datetime.fromisoformat(exp).date() - datetime.utcnow().date()).days

            quote = item.get("last_quote", {}) or {}
            bid = quote.get("bid")
            ask = quote.get("ask")
            mid = ((bid + ask) / 2) if bid is not None and ask is not None else None
            spread = _spread_pct(bid, ask)

            greeks = item.get("greeks", {}) or {}
            delta = greeks.get("delta")
            gamma = greeks.get("gamma")
            theta = greeks.get("theta")
            iv = item.get("implied_volatility")

            day = item.get("day", {}) or {}
            volume = day.get("volume") or 0
            oi = item.get("open_interest") or 0

            if spread is not None and spread > MAX_SPREAD_PCT:
                continue
            if volume < MIN_OPTION_VOLUME:
                continue
            if oi < MIN_OPTION_OI:
                continue
            if iv is not None and float(iv) > MAX_IV:
                continue
            if delta is not None and not (TARGET_MIN_DELTA <= abs(float(delta)) <= TARGET_MAX_DELTA):
                continue

            atm_score = -abs(strike - price)
            liq_score = (volume / 100) + (oi / 1000)
            spread_score = -(spread or MAX_SPREAD_PCT)
            iv_score = -(float(iv) * 5) if iv is not None else 0
            score = atm_score + liq_score + spread_score + iv_score

            if score > best_score:
                best_score = score
                best = OptionCandidate(
                    underlying=symbol,
                    contract_symbol=contract,
                    option_type=option_type.upper(),
                    strike=strike,
                    expiry=exp,
                    dte=dte,
                    bid=bid,
                    ask=ask,
                    mid=round(mid, 2) if mid else None,
                    spread_pct=round(spread, 2) if spread else None,
                    delta=round(float(delta), 3) if delta is not None else None,
                    gamma=round(float(gamma), 4) if gamma is not None else None,
                    theta=round(float(theta), 4) if theta is not None else None,
                    implied_volatility=round(float(iv), 3) if iv is not None else None,
                    volume=int(volume),
                    open_interest=int(oi),
                    status="OK",
                    reason="Liquid near-ATM contract selected with IV filter",
                )

    if best:
        return best

    return OptionCandidate(symbol, "", option_type.upper(), 0, "", 0, None, None, None, None, None, None, None, None, None, None, "SKIP", "No option passed liquidity, spread, delta, and IV filters")


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
        f"Delta: {candidate.delta} | IV: {candidate.implied_volatility} | Vol/OI: {candidate.volume}/{candidate.open_interest}"
    )
