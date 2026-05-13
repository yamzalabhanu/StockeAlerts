from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable

from openai import OpenAI
from playwright.async_api import async_playwright

from config import OPENAI_VISION_MODEL
from openai_models import chat_completion_options

from bot_utils import safe_float, safe_int
from symbol_utils import is_valid_symbol, normalize_symbol, tradingview_symbol

CHART_DIR = Path("charts")
CHART_DIR.mkdir(exist_ok=True)

DEFAULT_VISION_MODEL = OPENAI_VISION_MODEL
DEFAULT_VIEWPORT = {"width": 1440, "height": 1000}
VISION_FEATURES = (
    "failed_breakout",
    "compression",
    "wedge",
    "exhaustion",
    "trapped_traders",
    "liquidity_grab",
    "retest_confirmed",
    "late_breakout",
    "trend_quality",
)

VISION_DECISIONS = {"A+ CALL", "A+ PUT", "WAIT", "REJECT"}
LEGACY_DECISION_MAP = {"ENTER": "WAIT", "AVOID": "REJECT"}
TREND_DIRECTIONS = {"bullish", "bearish", "sideways", "unclear"}
MARKET_PHASES = {
    "opening_range",
    "trend_continuation",
    "pullback_retest",
    "breakout",
    "breakdown",
    "range",
    "reversal",
    "distribution",
    "accumulation",
    "chop",
    "unclear",
}
CONFIRMATION_STATES = {"confirmed", "partial", "missing", "failed", "unclear"}
RISK_STATES = {"low", "medium", "high", "unclear"}
ALIGNMENT_STATES = {"aligned", "mixed", "conflicting", "unavailable", "unclear"}
RISK_REWARD_STATES = {"viable", "marginal", "poor", "unclear"}
VOLUME_STATES = {"confirmed", "mixed", "weak", "climactic", "unavailable", "unclear"}

_JSON_SCHEMA = {
    "name": "vision_chart_reading",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "symbol": {"type": "string"},
            "timeframe": {"type": "string"},
            "decision": {"type": "string", "enum": ["A+ CALL", "A+ PUT", "WAIT", "REJECT"]},
            "direction": {"type": "string", "enum": ["bullish", "bearish", "sideways", "unclear"]},
            "trend_direction": {"type": "string", "enum": ["bullish", "bearish", "sideways", "unclear"]},
            "market_phase": {
                "type": "string",
                "enum": [
                    "opening_range",
                    "trend_continuation",
                    "pullback_retest",
                    "breakout",
                    "breakdown",
                    "range",
                    "reversal",
                    "distribution",
                    "accumulation",
                    "chop",
                    "unclear",
                ],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 100},
            "trend_quality": {"type": "string", "enum": ["strong", "healthy", "mixed", "choppy", "exhausted", "unclear"]},
            "pattern": {"type": "string"},
            "entry": {"type": ["string", "null"]},
            "stop": {"type": ["string", "null"]},
            "risk": {"type": "string", "enum": ["low", "medium", "high", "unclear"]},
            "retest_confirmation": {"type": "string", "enum": ["confirmed", "partial", "missing", "failed", "unclear"]},
            "late_breakout_risk": {"type": "string", "enum": ["low", "medium", "high", "unclear"]},
            "etf_alignment": {"type": "string", "enum": ["aligned", "mixed", "conflicting", "unavailable", "unclear"]},
            "volume_confirmation": {"type": "string", "enum": ["confirmed", "mixed", "weak", "climactic", "unavailable", "unclear"]},
            "risk_reward_viability": {"type": "string", "enum": ["viable", "marginal", "poor", "unclear"]},
            "atr_extension": {"type": ["number", "null"]},
            "features": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "failed_breakout": {"type": "boolean"},
                    "compression": {"type": "boolean"},
                    "wedge": {"type": "boolean"},
                    "exhaustion": {"type": "boolean"},
                    "trapped_traders": {"type": "boolean"},
                    "liquidity_grab": {"type": "boolean"},
                    "retest_confirmed": {"type": "boolean"},
                    "late_breakout": {"type": "boolean"},
                    "trend_quality": {"type": "string"},
                },
                "required": list(VISION_FEATURES),
            },
            "levels": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "support": {"type": ["string", "null"]},
                    "resistance": {"type": ["string", "null"]},
                    "liquidity": {"type": ["string", "null"]},
                    "invalidation": {"type": ["string", "null"]},
                    "orb_high": {"type": ["string", "null"]},
                    "orb_low": {"type": ["string", "null"]},
                    "premarket_high": {"type": ["string", "null"]},
                    "premarket_low": {"type": ["string", "null"]},
                    "previous_day_high": {"type": ["string", "null"]},
                    "previous_day_low": {"type": ["string", "null"]},
                },
                "required": [
                    "support",
                    "resistance",
                    "liquidity",
                    "invalidation",
                    "orb_high",
                    "orb_low",
                    "premarket_high",
                    "premarket_low",
                    "previous_day_high",
                    "previous_day_low",
                ],
            },
            "trapped_side": {"type": "string", "enum": ["longs", "shorts", "both", "none", "unclear"]},
            "etf_context": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "SPY": {"type": "string"},
                    "QQQ": {"type": "string"},
                    "SMH": {"type": "string"},
                    "VIX": {"type": "string"},
                },
                "required": ["SPY", "QQQ", "SMH", "VIX"],
            },
            "reasons": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
        "required": [
            "symbol",
            "timeframe",
            "decision",
            "direction",
            "trend_direction",
            "market_phase",
            "confidence",
            "trend_quality",
            "pattern",
            "entry",
            "stop",
            "risk",
            "retest_confirmation",
            "late_breakout_risk",
            "etf_alignment",
            "volume_confirmation",
            "risk_reward_viability",
            "atr_extension",
            "features",
            "levels",
            "trapped_side",
            "etf_context",
            "reasons",
            "warnings",
            "summary",
        ],
    },
    "strict": True,
}


def _openai_client() -> OpenAI:
    """Create the OpenAI client lazily so imports work without an API key."""
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _safe_symbol_for_file(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", symbol).strip("_") or "chart"


def _image_data_url(image_path: str | Path) -> str:
    path = Path(image_path)
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    suffix = path.suffix.lower()
    mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    return f"data:{mime};base64,{encoded}"


def _extract_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text or "", re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return {}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "confirmed", "present"}
    return bool(value)


def _normalize_enum(value: Any, allowed: set[str], default: str) -> str:
    normalized = str(value or default).strip().lower()
    return normalized if normalized in allowed else default


def _normalize_decision(value: Any, direction: str = "unclear") -> str:
    raw = str(value or "WAIT").strip().upper()
    if raw in VISION_DECISIONS:
        return raw
    if raw == "ENTER":
        if direction == "bullish":
            return "A+ CALL"
        if direction == "bearish":
            return "A+ PUT"
    return LEGACY_DECISION_MAP.get(raw, "WAIT")


def _normalize_etf_context(value: Any) -> dict[str, str]:
    context = value if isinstance(value, dict) else {}
    return {symbol: str(context.get(symbol) or "unavailable")[:120] for symbol in ("SPY", "QQQ", "SMH", "VIX")}


def _as_path_list(paths: str | Path | Iterable[str | Path] | None) -> list[str]:
    if paths is None:
        return []
    if isinstance(paths, (str, Path)):
        return [str(paths)]
    return [str(path) for path in paths if path]

def _clean_list(values: Any, limit: int = 8) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable):
        return []
    cleaned = []
    for item in values:
        text = str(item).strip()
        if text:
            cleaned.append(text[:240])
        if len(cleaned) >= limit:
            break
    return cleaned


def normalize_vision_reading(data: Dict[str, Any], symbol: str, timeframe: str) -> Dict[str, Any]:
    """Normalize AI vision JSON into the contract used by scoring and alerts."""
    data = data if isinstance(data, dict) else {}
    features = data.get("features") if isinstance(data.get("features"), dict) else {}
    levels = data.get("levels") if isinstance(data.get("levels"), dict) else {}

    direction = _normalize_enum(data.get("direction") or data.get("trend_direction"), TREND_DIRECTIONS, "unclear")
    trend_direction = _normalize_enum(data.get("trend_direction") or direction, TREND_DIRECTIONS, direction)
    decision = _normalize_decision(data.get("decision"), trend_direction)

    risk = _normalize_enum(data.get("risk"), RISK_STATES, "medium")
    market_phase = _normalize_enum(data.get("market_phase"), MARKET_PHASES, "unclear")
    retest_confirmation = _normalize_enum(data.get("retest_confirmation"), CONFIRMATION_STATES, "unclear")
    late_breakout_risk = _normalize_enum(data.get("late_breakout_risk"), RISK_STATES, "unclear")
    etf_alignment = _normalize_enum(data.get("etf_alignment"), ALIGNMENT_STATES, "unavailable")
    volume_confirmation = _normalize_enum(data.get("volume_confirmation"), VOLUME_STATES, "unclear")
    risk_reward_viability = _normalize_enum(data.get("risk_reward_viability"), RISK_REWARD_STATES, "unclear")

    trend_quality = str(data.get("trend_quality") or features.get("trend_quality") or "unclear").lower()
    if trend_quality not in {"strong", "healthy", "mixed", "choppy", "exhausted", "unclear"}:
        trend_quality = "unclear"

    trapped_side = str(data.get("trapped_side", "unclear")).lower()
    if trapped_side not in {"longs", "shorts", "both", "none", "unclear"}:
        trapped_side = "unclear"

    normalized_features = {
        "failed_breakout": _coerce_bool(features.get("failed_breakout")),
        "compression": _coerce_bool(features.get("compression")),
        "wedge": _coerce_bool(features.get("wedge")),
        "exhaustion": _coerce_bool(features.get("exhaustion")),
        "trapped_traders": _coerce_bool(features.get("trapped_traders")),
        "liquidity_grab": _coerce_bool(features.get("liquidity_grab")),
        "retest_confirmed": _coerce_bool(features.get("retest_confirmed") or retest_confirmation == "confirmed"),
        "late_breakout": _coerce_bool(features.get("late_breakout") or late_breakout_risk == "high"),
        "trend_quality": trend_quality,
    }

    return {
        "symbol": str(data.get("symbol") or symbol),
        "timeframe": str(data.get("timeframe") or timeframe),
        "decision": decision,
        "direction": direction,
        "trend_direction": trend_direction,
        "market_phase": market_phase,
        "confidence": max(0, min(safe_int(data.get("confidence", 50), 50), 100)),
        "trend_quality": trend_quality,
        "pattern": str(data.get("pattern", "unknown"))[:120],
        "entry": data.get("entry"),
        "stop": data.get("stop"),
        "risk": risk,
        "retest_confirmation": retest_confirmation,
        "late_breakout_risk": late_breakout_risk,
        "etf_alignment": etf_alignment,
        "volume_confirmation": volume_confirmation,
        "risk_reward_viability": risk_reward_viability,
        "atr_extension": safe_float(data.get("atr_extension")),
        "features": normalized_features,
        "levels": {
            "support": levels.get("support"),
            "resistance": levels.get("resistance"),
            "liquidity": levels.get("liquidity"),
            "invalidation": levels.get("invalidation"),
            "orb_high": levels.get("orb_high"),
            "orb_low": levels.get("orb_low"),
            "premarket_high": levels.get("premarket_high"),
            "premarket_low": levels.get("premarket_low"),
            "previous_day_high": levels.get("previous_day_high"),
            "previous_day_low": levels.get("previous_day_low"),
        },
        "trapped_side": trapped_side,
        "etf_context": _normalize_etf_context(data.get("etf_context")),
        "reasons": _clean_list(data.get("reasons")),
        "warnings": _clean_list(data.get("warnings")),
        "summary": str(data.get("summary", ""))[:600],
    }


def score_vision_reading(reading: Dict[str, Any], direction: str | None = None) -> Dict[str, Any]:
    """Convert a visual chart read into an objective score and quality bucket."""
    reading = reading or {}
    features = reading.get("features") or {}
    trade_direction = str(direction or "").upper()
    visual_direction = str(reading.get("direction", "unclear")).lower()
    confidence = safe_float(reading.get("confidence"), 50)

    score = 0
    tags: list[str] = []
    warnings: list[str] = list(reading.get("warnings") or [])[:5]

    if confidence >= 80:
        score += 8
    elif confidence < 55:
        score -= 6
        warnings.append("Low visual confidence")

    if features.get("compression"):
        score += 12
        tags.append("COMPRESSION")
    if features.get("retest_confirmed") or reading.get("retest_confirmation") == "confirmed":
        score += 14
        tags.append("RETEST_CONFIRMED")
    if features.get("liquidity_grab"):
        score += 6
        tags.append("LIQUIDITY_GRAB")
    if features.get("trapped_traders"):
        score += 5
        tags.append("TRAPPED_TRADERS")
    if features.get("wedge"):
        score += 3
        tags.append("WEDGE")

    trend_quality = str(reading.get("trend_quality") or features.get("trend_quality") or "unclear").lower()
    if trend_quality in {"strong", "healthy"}:
        score += 12 if trend_quality == "strong" else 8
        tags.append("QUALITY_TREND")
    elif trend_quality in {"choppy", "exhausted"}:
        score -= 12
        warnings.append(f"Visual trend quality is {trend_quality}")

    if features.get("failed_breakout"):
        score -= 18
        tags.append("FAILED_BREAKOUT")
        warnings.append("Vision detected a failed breakout")
    if features.get("exhaustion"):
        score -= 12
        tags.append("EXHAUSTION")
        warnings.append("Vision detected exhaustion candles")
    if features.get("late_breakout") or reading.get("late_breakout_risk") == "high":
        score -= 22
        tags.append("LATE_CHASE")
        warnings.append("Breakout is extended; wait for a cleaner retest")
    atr_extension = safe_float(reading.get("atr_extension"))
    if atr_extension is not None and atr_extension > 1.5:
        score -= 25
        tags.append("EXTENDED_GT_1_5_ATR")
        warnings.append("Breakout extension is greater than 1.5 ATR")

    if reading.get("etf_alignment") == "aligned":
        score += 8
        tags.append("ETF_ALIGNED")
    elif reading.get("etf_alignment") == "conflicting":
        score -= 14
        warnings.append("ETF alignment conflicts with setup direction")

    if reading.get("volume_confirmation") == "confirmed":
        score += 8
        tags.append("VOLUME_CONFIRMED")
    elif reading.get("volume_confirmation") in {"weak", "climactic"}:
        score -= 8
        warnings.append(f"Volume confirmation is {reading.get('volume_confirmation')}")

    if reading.get("risk_reward_viability") == "viable":
        score += 8
        tags.append("RR_VIABLE")
    elif reading.get("risk_reward_viability") == "poor":
        score -= 15
        warnings.append("Risk/reward is not viable")

    if trade_direction == "CALL" and visual_direction == "bullish":
        score += 8
    elif trade_direction == "PUT" and visual_direction == "bearish":
        score += 8
    elif trade_direction in {"CALL", "PUT"} and visual_direction in {"bullish", "bearish"}:
        score -= 10
        warnings.append(f"Visual direction conflicts with {trade_direction}: {visual_direction}")

    decision = reading.get("decision")
    if decision == "ENTER" or (decision == "A+ CALL" and trade_direction in {"", "CALL"}) or (
        decision == "A+ PUT" and trade_direction in {"", "PUT"}
    ):
        score += 8
    elif decision in {"A+ CALL", "A+ PUT"}:
        score -= 12
        warnings.append(f"Vision decision conflicts with {trade_direction}: {decision}")
    elif decision in {"REJECT", "AVOID"}:
        score -= 15
        warnings.append(f"Vision decision is {decision}")

    if score >= 30:
        quality = "ELITE"
    elif score >= 15:
        quality = "GOOD"
    elif score >= 0:
        quality = "NEUTRAL"
    else:
        quality = "POOR"

    return {
        "quality": quality,
        "score": round(score, 2),
        "tags": tags,
        "warnings": warnings,
        "reading": reading,
    }


async def capture_chart(symbol: str, timeframe: str = "D", filename: str | None = None) -> str:
    """Capture a TradingView chart screenshot for visual confirmation."""
    clean_symbol = normalize_symbol(symbol.split(":")[-1])
    if not is_valid_symbol(clean_symbol):
        raise ValueError(f"Invalid symbol for chart capture: {symbol}")

    tv_symbol = symbol if ":" in symbol else tradingview_symbol(clean_symbol)
    clean_file_symbol = _safe_symbol_for_file(tv_symbol)
    filename = filename or str(CHART_DIR / f"{clean_file_symbol}_{timeframe}.png")
    url = f"https://www.tradingview.com/chart/?symbol={tv_symbol}&interval={timeframe}&theme=dark"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport=DEFAULT_VIEWPORT, device_scale_factor=1)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        await page.screenshot(path=str(filename), full_page=False)
        await browser.close()

    return str(filename)


async def capture_multi_timeframe_charts(symbol: str, timeframes: Iterable[str] = ("1", "5", "15")) -> list[str]:
    """Capture the intraday 1m/5m/15m stack used for A+ options entries."""
    paths = []
    for timeframe in timeframes:
        paths.append(await capture_chart(symbol, timeframe=str(timeframe)))
    return paths


def build_vision_prompt(symbol: str, timeframe: str, analysis: Dict[str, Any] | None = None) -> str:
    context = json.dumps(analysis or {}, default=str, sort_keys=True)[:4000]
    return (
        f"You are an elite institutional intraday trader analyzing options entries for {symbol} on {timeframe}.\n"
        f"Structured technical context, ETF context, ORB/PMH/PML levels, if any: {context}\n\n"
        "Primary objective: strictly classify the setup as A+ CALL, A+ PUT, WAIT, or REJECT. "
        "Priority order: 1) market structure, 2) price action, 3) trend quality, 4) retest quality, "
        "5) entry timing, 6) risk/reward, 7) indicators only as secondary evidence. "
        "Use the current screenshot stack plus any prior sequence screenshots as memory; check 1m/5m/15m alignment when provided. "
        "Explicitly determine trend_direction, market_phase, retest_confirmation, late_breakout_risk, "
        "ETF alignment from SPY/QQQ/SMH/VIX context, volume_confirmation, and risk_reward_viability. "
        "Respect ORB high/low, premarket high/low, and previous-day high/low overlays or context as key decision levels. "
        "Avoid chasing extended moves: if the breakout is already extended more than 1.5 ATR without a clean retest, prefer WAIT. "
        "Detect liquidity grabs above/below obvious levels and reject failed breakouts, exhaustion, conflicting ETF tape, poor R/R, or unreadable screenshots. "
        "Return structured JSON only matching the schema."
    )


async def analyze_chart_vision(
    symbol: str,
    analysis: Dict[str, Any] | None = None,
    timeframe: str = "D",
    image_path: str | None = None,
    image_paths: Iterable[str | Path] | None = None,
    screenshot_sequence: Iterable[str | Path] | None = None,
    model: str = DEFAULT_VISION_MODEL,
    client: OpenAI | None = None,
) -> Dict[str, Any]:
    """Send chart screenshots to OpenAI Vision and return normalized intraday analysis.

    `image_paths` supports the recommended current 1m/5m/15m stack.
    `screenshot_sequence` can include up to three prior screenshots as sequence
    memory so the model can judge whether the entry is early or already chased.
    """
    current_images = _as_path_list(image_paths)
    if image_path:
        current_images.insert(0, str(image_path))
    if not current_images:
        current_images = [await capture_chart(symbol, timeframe=timeframe)]

    sequence_images = _as_path_list(screenshot_sequence)[:3]
    content: list[dict[str, Any]] = [{"type": "text", "text": build_vision_prompt(symbol, timeframe, analysis)}]
    for path in current_images:
        content.append({"type": "image_url", "image_url": {"url": _image_data_url(path), "detail": "high"}})
    for path in sequence_images:
        content.append({"type": "image_url", "image_url": {"url": _image_data_url(path), "detail": "low"}})

    response = (client or _openai_client()).chat.completions.create(
        **chat_completion_options(
            model=model,
            temperature=0.1,
            response_format={"type": "json_schema", "json_schema": _JSON_SCHEMA},
            messages=[{"role": "user", "content": content}],
        )
    )
    content_text = response.choices[0].message.content
    return normalize_vision_reading(_extract_json(content_text), symbol, timeframe)


async def analyze_chart_ai(symbol: str, analysis: dict | None = None) -> str:
    """Backward-compatible text summary of the richer AI vision chart reading."""
    reading = await analyze_chart_vision(symbol, analysis=analysis)
    features = reading.get("features", {})
    active_features = [name for name, present in features.items() if name != "trend_quality" and present]
    return (
        f"Decision: {reading['decision']}\n"
        f"Trend: {reading['direction']} ({reading['trend_quality']})\n"
        f"Pattern: {reading['pattern']}\n"
        f"Entry: {reading.get('entry') or 'N/A'}\n"
        f"Stop: {reading.get('stop') or 'N/A'}\n"
        f"Risk: {reading['risk']}\n"
        f"Detected: {', '.join(active_features) if active_features else 'none'}\n"
        f"Reason: {reading.get('summary') or '; '.join(reading.get('reasons', []))}"
    )
