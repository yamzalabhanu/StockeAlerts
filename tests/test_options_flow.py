import unittest

from unittest.mock import patch

from options_engine import analyze_options_flow, format_options_flow, options_flow_to_dict


class FakeOptionsClient:
    configured = True

    def option_snapshots(self, underlying, **params):
        contract_type = params.get("contract_type")
        if contract_type == "call":
            return [
                {
                    "details": {"ticker": "O:XYZ990115C00100000", "contract_type": "call", "strike_price": 100, "expiration_date": "2099-01-15"},
                    "day": {"volume": 5000, "close": 5.0},
                    "open_interest": 6000,
                    "greeks": {"delta": 0.62, "gamma": 0.08},
                    "implied_volatility": 1.8,
                },
                {
                    "details": {"ticker": "O:XYZ990115C00105000", "contract_type": "call", "strike_price": 105, "expiration_date": "2099-01-15"},
                    "day": {"volume": 1800, "close": 3.0},
                    "open_interest": 9000,
                    "greeks": {"delta": 0.45, "gamma": 0.05},
                    "implied_volatility": 1.6,
                },
            ]
        return [
            {
                "details": {"ticker": "O:XYZ990115P00095000", "contract_type": "put", "strike_price": 95, "expiration_date": "2099-01-15"},
                "day": {"volume": 300, "close": 2.0},
                "open_interest": 8000,
                "greeks": {"delta": -0.32, "gamma": 0.02},
                "implied_volatility": 1.1,
            }
        ]

    def option_trades(self, option_ticker, **params):
        if option_ticker.endswith("C00100000"):
            return [
                {"price": 5.25, "size": 600, "sip_timestamp": 1},
                {"price": 5.3, "size": 500, "sip_timestamp": 2},
            ]
        return []


class MissingOptionsClient:
    configured = False


class OptionsFlowTests(unittest.TestCase):
    def test_analyze_options_flow_detects_sweeps_walls_and_gamma_squeeze(self):
        with patch("options_engine.FLOW_EXPIRY_DAYS", 30000):
            report = analyze_options_flow("XYZ", "CALL", client=FakeOptionsClient())

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.bias, "BULLISH")
        self.assertGreaterEqual(report.score, 70)
        self.assertTrue(report.gamma_squeeze)
        self.assertEqual(report.put_wall_strike, 95)
        self.assertEqual(report.call_wall_strike, 105)

        signal_names = {signal.name for signal in report.signals}
        self.assertIn("aggressive_call_sweeps", signal_names)
        self.assertIn("put_wall", signal_names)
        self.assertIn("delta_imbalance", signal_names)
        self.assertIn("gamma_squeeze_conditions", signal_names)

    def test_options_flow_dict_and_format_are_alert_safe(self):
        with patch("options_engine.FLOW_EXPIRY_DAYS", 30000):
            report = analyze_options_flow("XYZ", "CALL", client=FakeOptionsClient())
        data = options_flow_to_dict(report)
        text = format_options_flow(report)

        self.assertEqual(data["underlying"], "XYZ")
        self.assertIsInstance(data["signals"][0], dict)
        self.assertIn("Options Flow", text)
        self.assertIn("BULLISH", text)

    def test_missing_api_key_returns_skip_report(self):
        report = analyze_options_flow("XYZ", "CALL", client=MissingOptionsClient())

        self.assertEqual(report.status, "SKIP")
        self.assertEqual(report.score, 0)
        self.assertIn("API key", report.reason)


if __name__ == "__main__":
    unittest.main()
