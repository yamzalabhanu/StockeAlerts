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
    "trend_quality",
)

_JSON_SCHEMA = {
    "name": "vision_chart_reading",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "symbol": {"type": "string"},
            "timeframe": {"type": "string"},
            "decision": {"type": "string", "enum": ["ENTER", "WAIT", "AVOID"]},
            "direction": {"type": "string", "enum": ["bullish", "bearish", "sideways", "unclear"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 100},
            "trend_quality": {"type": "string", "enum": ["strong", "healthy", "mixed", "choppy", "exhausted", "unclear"]},
            "pattern": {"type": "string"},
            "entry": {"type": ["string", "null"]},
            "stop": {"type": ["string", "null"]},
            "risk": {"type": "string", "enum": ["low", "medium", "high"]},
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
                },
                "required": ["support", "resistance", "liquidity", "invalidation"],
            },
            "trapped_side": {"type": "string", "enum": ["longs", "shorts", "both", "none", "unclear"]},
            "reasons": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
        "required": [
            "symbol",
            "timeframe",
            "decision",
            "direction",
            "confidence",
            "trend_quality",
            "pattern",
            "entry",
            "stop",
            "risk",
            "features",
            "levels",
            "trapped_side",
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

    decision = str(data.get("decision", "WAIT")).upper()
    if decision not in {"ENTER", "WAIT", "AVOID"}:
        decision = "WAIT"

    direction = str(data.get("direction", "unclear")).lower()
    if direction not in {"bullish", "bearish", "sideways", "unclear"}:
        direction = "unclear"

    risk = str(data.get("risk", "medium")).lower()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"

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
        "trend_quality": trend_quality,
    }

    return {
        "symbol": str(data.get("symbol") or symbol),
        "timeframe": str(data.get("timeframe") or timeframe),
        "decision": decision,
        "direction": direction,
        "confidence": max(0, min(safe_int(data.get("confidence", 50), 50), 100)),
        "trend_quality": trend_quality,
        "pattern": str(data.get("pattern", "unknown"))[:120],
        "entry": data.get("entry"),
        "stop": data.get("stop"),
        "risk": risk,
        "features": normalized_features,
        "levels": {
            "support": levels.get("support"),
            "resistance": levels.get("resistance"),
            "liquidity": levels.get("liquidity"),
            "invalidation": levels.get("invalidation"),
        },
        "trapped_side": trapped_side,
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

    if trade_direction == "CALL" and visual_direction == "bullish":
        score += 8
    elif trade_direction == "PUT" and visual_direction == "bearish":
        score += 8
    elif trade_direction in {"CALL", "PUT"} and visual_direction in {"bullish", "bearish"}:
        score -= 10
        warnings.append(f"Visual direction conflicts with {trade_direction}: {visual_direction}")

    if reading.get("decision") == "ENTER":
        score += 8
    elif reading.get("decision") == "AVOID":
        score -= 15
        warnings.append("Vision decision is AVOID")

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


def build_vision_prompt(symbol: str, timeframe: str, analysis: Dict[str, Any] | None = None) -> str:
    context = json.dumps(analysis or {}, default=str, sort_keys=True)[:3000]
    return (
        f"You are an expert discretionary chart reader analyzing a TradingView screenshot for {symbol} on {timeframe}.\n"
        f"Structured technical context, if any: {context}\n\n"
        "Read the candles visually, not just the supplied data. Detect and explain these edge cases: "
        "failed breakouts, volatility compression, wedges, exhaustion candles, trapped traders, "
        "liquidity grabs above/below obvious levels, and overall trend quality. "
        "Favor WAIT/AVOID if the screenshot is unreadable, price is extended, the breakout already failed, "
        "or the move appears to be a late chase. Return only JSON matching the schema."
    )


async def analyze_chart_vision(
    symbol: str,
    analysis: Dict[str, Any] | None = None,
    timeframe: str = "D",
    image_path: str | None = None,
    model: str = DEFAULT_VISION_MODEL,
    client: OpenAI | None = None,
) -> Dict[str, Any]:
    """Screenshot a TradingView chart, send it to OpenAI Vision, and return normalized analysis."""
    image_path = image_path or await capture_chart(symbol, timeframe=timeframe)
    response = (client or _openai_client()).chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_schema", "json_schema": _JSON_SCHEMA},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_vision_prompt(symbol, timeframe, analysis)},
                    {"type": "image_url", "image_url": {"url": _image_data_url(image_path), "detail": "high"}},
                ],
            }
        ],
    )
    content = response.choices[0].message.content
    return normalize_vision_reading(_extract_json(content), symbol, timeframe)


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
