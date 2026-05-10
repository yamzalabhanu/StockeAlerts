from __future__ import annotations

from typing import Any, Mapping, Optional


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_money(value: Any) -> str:
    number = _safe_float(value)
    if number is None:
        return "n/a"
    return f"${number:.2f}"


def _fmt_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def format_predicted_price_move(
    direction: str,
    entry: Any,
    target: Any,
    stop: Any = None,
) -> str:
    """Build a Telegram-safe one-line forecast from entry/target/stop prices."""
    entry_float = _safe_float(entry)
    target_float = _safe_float(target)
    stop_float = _safe_float(stop)
    if not entry_float or target_float is None:
        return ""

    direction_text = str(direction or "").upper()
    if direction_text == "PUT":
        target_move = entry_float - target_float
        stop_risk = (stop_float - entry_float) if stop_float is not None else None
    else:
        target_move = target_float - entry_float
        stop_risk = (entry_float - stop_float) if stop_float is not None else None

    target_pct = (target_move / entry_float) * 100
    target_sign = "+" if target_move >= 0 else ""
    line = (
        f"📊 Predicted Price Move: {target_sign}${target_move:.2f} "
        f"({_fmt_pct(target_pct)}) toward {_fmt_money(target_float)}"
    )

    if stop_risk is not None:
        risk_pct = (stop_risk / entry_float) * 100
        risk_sign = "+" if stop_risk >= 0 else ""
        line += f" | Stop Risk {risk_sign}${stop_risk:.2f} ({_fmt_pct(risk_pct)})"

    return line + "\n"


def _format_estimated_contract_move(
    option_contract: Mapping[str, Any],
    direction: str,
    entry: Any,
    target: Any,
) -> str:
    entry_float = _safe_float(entry)
    target_float = _safe_float(target)
    mid = _safe_float(option_contract.get("mid"))
    delta = _safe_float(option_contract.get("delta"))
    if not entry_float or target_float is None or not mid or delta is None:
        return ""

    direction_text = str(direction or option_contract.get("option_type") or "").upper()
    underlying_move = entry_float - target_float if direction_text == "PUT" else target_float - entry_float
    estimated_premium_change = abs(delta) * abs(underlying_move)
    estimated_target_mid = mid + estimated_premium_change
    estimated_pct = (estimated_premium_change / mid) * 100 if mid else 0

    return (
        "📈 Est. Contract Move: "
        f"{_fmt_money(mid)} → {_fmt_money(estimated_target_mid)} "
        f"(+{estimated_pct:.1f}%) if target hits (delta-only)\n"
    )


def format_recommended_option_contract(
    option_contract: Mapping[str, Any] | Any,
    *,
    direction: str = "",
    entry: Any = None,
    target: Any = None,
) -> str:
    """Format a detailed recommended options contract block for Telegram alerts."""
    if not option_contract:
        return ""

    if not isinstance(option_contract, Mapping):
        option_contract = getattr(option_contract, "__dict__", {})

    if option_contract.get("status") != "OK":
        return ""

    lines = [
        f"\n🎯 Recommended Contract: {option_contract.get('contract_symbol')}",
        (
            "📄 "
            f"{option_contract.get('option_type')} | Strike {_fmt_money(option_contract.get('strike'))} | "
            f"Exp {option_contract.get('expiry')} ({option_contract.get('dte')} DTE)"
        ),
        (
            "💵 "
            f"Bid/Ask/Mid {_fmt_money(option_contract.get('bid'))}/"
            f"{_fmt_money(option_contract.get('ask'))}/{_fmt_money(option_contract.get('mid'))} | "
            f"Spread {option_contract.get('spread_pct')}%"
        ),
        (
            "📊 "
            f"Vol/OI {option_contract.get('volume')}/{option_contract.get('open_interest')} "
            f"({option_contract.get('volume_oi_ratio')}) | "
            f"Score {option_contract.get('recommendation_score')}"
        ),
    ]

    greek_line_parts = []
    if option_contract.get("delta") is not None:
        greek_line_parts.append(f"Δ {option_contract.get('delta')}")
    if option_contract.get("theta") is not None:
        greek_line_parts.append(f"Θ {option_contract.get('theta')}")
    if option_contract.get("implied_volatility") is not None:
        greek_line_parts.append(f"IV {option_contract.get('implied_volatility')}")
    if greek_line_parts:
        lines.append("🧮 " + " | ".join(greek_line_parts))

    estimated_move_line = _format_estimated_contract_move(option_contract, direction, entry, target).rstrip()
    if estimated_move_line:
        lines.append(estimated_move_line)

    return "\n".join(lines) + "\n"
