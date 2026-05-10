import unittest

from unittest.mock import patch

from options_engine import analyze_options_flow, format_options_flow, options_flow_to_dict, recommend_option_contracts_from_chain, select_option_contract


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


class FakeSelectionClient:
    configured = True

    def option_snapshots(self, underlying, **params):
        expiry = params.get("expiration_date", "2099-01-15")
        return [
            {
                "details": {"ticker": "O:XYZTESTC00100000", "contract_type": "call", "strike_price": 100, "expiration_date": expiry},
                "last_quote": {"bid": 4.9, "ask": 5.1},
                "day": {"volume": 900},
                "open_interest": 5000,
                "greeks": {"delta": 0.52, "gamma": 0.04, "theta": -0.08},
                "implied_volatility": 0.58,
            },
            {
                "details": {"ticker": "O:XYZTESTC00105000", "contract_type": "call", "strike_price": 105, "expiration_date": expiry},
                "last_quote": {"bid": 2.4, "ask": 2.7},
                "day": {"volume": 5000},
                "open_interest": 12000,
                "greeks": {"delta": 0.47, "gamma": 0.05, "theta": -0.07},
                "implied_volatility": 0.62,
            },
            {
                "details": {"ticker": "O:XYZTESTC00110000", "contract_type": "call", "strike_price": 110, "expiration_date": expiry},
                "last_quote": {"bid": 1.0, "ask": 1.8},
                "day": {"volume": 20000},
                "open_interest": 100,
                "greeks": {"delta": 0.25},
                "implied_volatility": 0.7,
            },
        ]

    def option_trades(self, option_ticker, **params):
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


    def test_select_option_contract_recommends_high_oi_volume_candidate(self):
        with patch("options_engine._next_fridays", return_value=["2099-01-15"]), \
             patch("options_engine.MIN_DTE", 1), \
             patch("options_engine.MAX_DTE", 30000):
            candidate = select_option_contract(
                "XYZ",
                {"signal": "CALL", "price": 101},
                client=FakeSelectionClient(),
            )

        self.assertEqual(candidate.status, "OK")
        self.assertEqual(candidate.contract_symbol, "O:XYZTESTC00105000")
        self.assertGreater(candidate.recommendation_score, 0)
        self.assertGreater(candidate.liquidity_score, 0)
        self.assertAlmostEqual(candidate.volume_oi_ratio, round(5000 / 12000, 3))
        self.assertIn("OI", candidate.reason)

    def test_recommend_option_contracts_from_chain_ranks_by_volume_and_oi(self):
        chain = [
            {
                "details": {"ticker": "O:XYZTESTC00100000", "contract_type": "call", "strike_price": 100, "expiration_date": "2099-01-15"},
                "last_quote": {"bid": 4.9, "ask": 5.1},
                "day": {"volume": 900},
                "open_interest": 5000,
                "greeks": {"delta": 0.52, "gamma": 0.04, "theta": -0.08},
                "implied_volatility": 0.58,
            },
            {
                "details": {"ticker": "O:XYZTESTC00105000", "contract_type": "call", "strike_price": 105, "expiration_date": "2099-01-15"},
                "last_quote": {"bid": 2.4, "ask": 2.7},
                "day": {"volume": 5000},
                "open_interest": 12000,
                "greeks": {"delta": 0.47, "gamma": 0.05, "theta": -0.07},
                "implied_volatility": 0.62,
            },
            {
                "details": {"ticker": "O:XYZTESTC00110000", "contract_type": "call", "strike_price": 110, "expiration_date": "2099-01-15"},
                "last_quote": {"bid": 1.0, "ask": 1.8},
                "day": {"volume": 20000},
                "open_interest": 100,
                "greeks": {"delta": 0.25},
                "implied_volatility": 0.7,
            },
        ]

        with patch("options_engine.MIN_DTE", 1), patch("options_engine.MAX_DTE", 30000):
            candidates = recommend_option_contracts_from_chain(
                "XYZ",
                chain,
                {"signal": "CALL", "price": 101},
                top_n=2,
            )

        self.assertEqual([candidate.contract_symbol for candidate in candidates], [
            "O:XYZTESTC00105000",
            "O:XYZTESTC00100000",
        ])
        self.assertTrue(all(candidate.status == "OK" for candidate in candidates))
        self.assertGreater(candidates[0].open_interest, candidates[1].open_interest)
        self.assertGreater(candidates[0].volume, candidates[1].volume)
        self.assertIn("option-chain liquidity", candidates[0].reason)

    def test_recommend_option_contracts_prefers_liquidity_over_atm_score(self):
        chain = [
            {
                "details": {"ticker": "O:XYZTESTC00100000", "contract_type": "call", "strike_price": 100, "expiration_date": "2099-01-15"},
                "last_quote": {"bid": 2.95, "ask": 3.05},
                "day": {"volume": 1200},
                "open_interest": 10000,
                "greeks": {"delta": 0.5},
                "implied_volatility": 0.5,
            },
            {
                "details": {"ticker": "O:XYZTESTC00112000", "contract_type": "call", "strike_price": 112, "expiration_date": "2099-01-15"},
                "last_quote": {"bid": 1.95, "ask": 2.05},
                "day": {"volume": 15000},
                "open_interest": 50000,
                "greeks": {"delta": 0.35},
                "implied_volatility": 0.5,
            },
        ]

        with patch("options_engine.MIN_DTE", 1), patch("options_engine.MAX_DTE", 30000):
            candidates = recommend_option_contracts_from_chain(
                "XYZ",
                chain,
                {"signal": "CALL", "price": 100},
                top_n=2,
            )

        self.assertEqual(candidates[0].contract_symbol, "O:XYZTESTC00112000")
        self.assertGreater(candidates[0].volume, candidates[1].volume)
        self.assertGreater(candidates[0].open_interest, candidates[1].open_interest)
        self.assertGreater(candidates[1].recommendation_score, candidates[0].recommendation_score)

    def test_recommend_option_contracts_never_penalizes_higher_volume_and_oi_for_lower_turnover(self):
        chain = [
            {
                "details": {"ticker": "O:XYZTESTC00100000", "contract_type": "call", "strike_price": 100, "expiration_date": "2099-01-15"},
                "last_quote": {"bid": 2.95, "ask": 3.05},
                "day": {"volume": 900},
                "open_interest": 900,
                "greeks": {"delta": 0.5},
                "implied_volatility": 0.5,
            },
            {
                "details": {"ticker": "O:XYZTESTC00105000", "contract_type": "call", "strike_price": 105, "expiration_date": "2099-01-15"},
                "last_quote": {"bid": 2.4, "ask": 2.6},
                "day": {"volume": 3000},
                "open_interest": 20000,
                "greeks": {"delta": 0.45},
                "implied_volatility": 0.5,
            },
        ]

        with patch("options_engine.MIN_DTE", 1), patch("options_engine.MAX_DTE", 30000):
            candidates = recommend_option_contracts_from_chain(
                "XYZ",
                chain,
                {"signal": "CALL", "price": 100},
                top_n=2,
            )

        self.assertEqual(candidates[0].contract_symbol, "O:XYZTESTC00105000")
        self.assertGreater(candidates[0].volume, candidates[1].volume)
        self.assertGreater(candidates[0].open_interest, candidates[1].open_interest)
        self.assertGreater(candidates[1].volume_oi_ratio, candidates[0].volume_oi_ratio)

    def test_option_volume_and_oi_provider_aliases_are_used(self):
        chain = [
            {
                "details": {
                    "ticker": "O:XYZTESTC00105000",
                    "contract_type": "call",
                    "strike_price": 105,
                    "expiration_date": "2099-01-15",
                    "openInterest": 25000,
                },
                "last_quote": {"bid": 2.4, "ask": 2.7},
                "day": {"v": 8000},
                "greeks": {"delta": 0.47},
                "implied_volatility": 0.62,
            }
        ]

        with patch("options_engine.MIN_DTE", 1), patch("options_engine.MAX_DTE", 30000):
            candidates = recommend_option_contracts_from_chain(
                "XYZ",
                chain,
                {"signal": "CALL", "price": 101},
            )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].volume, 8000)
        self.assertEqual(candidates[0].open_interest, 25000)

    def test_missing_api_key_returns_skip_report(self):
        report = analyze_options_flow("XYZ", "CALL", client=MissingOptionsClient())

        self.assertEqual(report.status, "SKIP")
        self.assertEqual(report.score, 0)
        self.assertIn("API key", report.reason)


if __name__ == "__main__":
    unittest.main()
