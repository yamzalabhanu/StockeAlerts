import unittest

from symbol_utils import tradingview_candidates, tradingview_symbol
from chart_ai import _tradingview_capture_candidates


class TradingViewSymbolTests(unittest.TestCase):
    def test_qbts_uses_nyse_on_tradingview(self):
        self.assertEqual(tradingview_symbol("QBTS"), "NYSE:QBTS")
        self.assertEqual(tradingview_candidates("QBTS")[:3], ["NYSE:QBTS", "NASDAQ:QBTS", "AMEX:QBTS"])

    def test_explicit_exchange_can_fallback_to_known_candidate(self):
        self.assertEqual(
            _tradingview_capture_candidates("NASDAQ:QBTS", "QBTS")[:2],
            ["NASDAQ:QBTS", "NYSE:QBTS"],
        )


if __name__ == "__main__":
    unittest.main()
