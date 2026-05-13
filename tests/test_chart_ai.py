import asyncio
import base64
import json
import tempfile
import unittest
from pathlib import Path
from chart_ai import DEFAULT_VISION_MODEL, analyze_chart_vision, normalize_vision_reading, score_vision_reading
from vision_ai import score_chart_structure


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Message(content)


class _Response:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Completions:
    def __init__(self, content):
        self.content = content
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _Response(self.content)


class _Chat:
    def __init__(self, completions):
        self.completions = completions


class _Client:
    def __init__(self, content):
        self.chat = _Chat(_Completions(content))


class ChartVisionTests(unittest.TestCase):
    def test_normalize_vision_reading_detects_required_edge_fields(self):
        reading = normalize_vision_reading(
            {
                "decision": "enter",
                "direction": "Bullish",
                "confidence": 91,
                "trend_quality": "strong",
                "pattern": "tight bull flag after liquidity sweep",
                "risk": "low",
                "features": {
                    "failed_breakout": False,
                    "compression": "yes",
                    "wedge": False,
                    "exhaustion": False,
                    "trapped_traders": True,
                    "liquidity_grab": True,
                    "trend_quality": "strong",
                },
                "levels": {"support": "100", "resistance": "110", "liquidity": "111", "invalidation": "98"},
                "trapped_side": "shorts",
                "reasons": ["higher lows", "tight ranges"],
                "warnings": [],
                "summary": "Compression with shorts trapped above prior resistance.",
            },
            "TEST",
            "D",
        )

        self.assertEqual(reading["decision"], "A+ CALL")
        self.assertEqual(reading["trend_direction"], "bullish")
        self.assertEqual(reading["market_phase"], "unclear")
        self.assertEqual(reading["etf_alignment"], "unavailable")
        self.assertTrue(reading["features"]["compression"])
        self.assertTrue(reading["features"]["liquidity_grab"])
        self.assertEqual(reading["trapped_side"], "shorts")

    def test_score_vision_reading_penalizes_failed_breakout_and_exhaustion(self):
        result = score_vision_reading(
            {
                "decision": "AVOID",
                "direction": "bearish",
                "confidence": 88,
                "trend_quality": "exhausted",
                "features": {
                    "failed_breakout": True,
                    "compression": False,
                    "wedge": True,
                    "exhaustion": True,
                    "trapped_traders": True,
                    "liquidity_grab": True,
                },
                "warnings": [],
            },
            "CALL",
        )

        self.assertEqual(result["quality"], "POOR")
        self.assertIn("FAILED_BREAKOUT", result["tags"])
        self.assertTrue(any("failed breakout" in warning.lower() for warning in result["warnings"]))


    def test_score_vision_reading_waits_on_extended_breakout_without_retest(self):
        result = score_vision_reading(
            normalize_vision_reading(
                {
                    "decision": "WAIT",
                    "direction": "bullish",
                    "atr_extension": 1.8,
                    "late_breakout_risk": "high",
                    "retest_confirmation": "missing",
                    "risk_reward_viability": "poor",
                    "features": {"late_breakout": True},
                },
                "TEST",
                "1/5/15",
            ),
            "CALL",
        )

        self.assertEqual(result["quality"], "POOR")
        self.assertIn("EXTENDED_GT_1_5_ATR", result["tags"])
        self.assertTrue(any("1.5 ATR" in warning for warning in result["warnings"]))

    def test_score_chart_structure_merges_visual_reading(self):
        result = score_chart_structure(
            {
                "candle_body_pct": 70,
                "rel_volume": 2.2,
                "vision_chart": {
                    "decision": "ENTER",
                    "direction": "bullish",
                    "confidence": 90,
                    "trend_quality": "strong",
                    "features": {
                        "compression": True,
                        "liquidity_grab": True,
                        "trapped_traders": True,
                    },
                },
            },
            "CALL",
        )

        self.assertEqual(result["quality"], "ELITE")
        self.assertIn("LIQUIDITY_GRAB", result["tags"])
        self.assertEqual(result["visual"]["quality"], "ELITE")

    def test_analyze_chart_vision_sends_screenshot_and_schema_prompt(self):
        payload = {
            "symbol": "TEST",
            "timeframe": "D",
            "decision": "WAIT",
            "direction": "sideways",
            "confidence": 64,
            "trend_quality": "mixed",
            "pattern": "compression",
            "entry": "above 10.50",
            "stop": "below 9.80",
            "risk": "medium",
            "features": {
                "failed_breakout": False,
                "compression": True,
                "wedge": False,
                "exhaustion": False,
                "trapped_traders": False,
                "liquidity_grab": False,
                "trend_quality": "mixed",
            },
            "levels": {"support": "9.80", "resistance": "10.50", "liquidity": None, "invalidation": "9.80"},
            "trapped_side": "none",
            "reasons": ["range tightening"],
            "warnings": ["needs trigger"],
            "summary": "Range is compressing but no confirmed break yet.",
        }
        client = _Client(json.dumps(payload))

        with tempfile.TemporaryDirectory() as tmpdir:
            image = Path(tmpdir) / "chart.png"
            image.write_bytes(base64.b64decode("iVBORw0KGgo="))
            reading = asyncio.run(analyze_chart_vision("TEST", {"price": 10}, image_path=str(image), client=client))

        kwargs = client.chat.completions.kwargs
        self.assertEqual(reading["decision"], "WAIT")
        self.assertEqual(kwargs["model"], DEFAULT_VISION_MODEL)
        self.assertEqual(DEFAULT_VISION_MODEL, "gpt-5-mini")
        self.assertEqual(kwargs["response_format"]["type"], "json_schema")
        self.assertEqual(kwargs["reasoning_effort"], "medium")
        self.assertNotIn("temperature", kwargs)
        text = kwargs["messages"][0]["content"][0]["text"]
        self.assertIn("failed breakouts", text)
        self.assertIn("liquidity grabs", text)
        self.assertIn("A+ CALL, A+ PUT, WAIT, or REJECT", text)
        self.assertIn("SPY/QQQ/SMH/VIX", text)
        self.assertTrue(kwargs["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
