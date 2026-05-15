import unittest

from config import (
    AUTO_WATCHLIST_LIMIT,
    BASE_WATCHLIST,
    CORE_WATCHLIST,
    DEPRIORITIZED_INTRADAY_OPTIONS,
    SECONDARY_WATCHLIST,
    SPEC_WATCHLIST,
    normalize_api_key,
)


class ApiKeyNormalizationTests(unittest.TestCase):
    def test_strips_bearer_prefix_for_sdk_authorization(self):
        self.assertEqual(normalize_api_key("Bearer polygon-key"), "polygon-key")

    def test_strips_authorization_header_label(self):
        self.assertEqual(
            normalize_api_key("Authorization: Bearer polygon-key"), "polygon-key"
        )

    def test_extracts_copied_query_param_value(self):
        self.assertEqual(
            normalize_api_key("https://api.polygon.io/v2/aggs?apiKey=polygon-key"),
            "polygon-key",
        )

    def test_preserves_plain_key(self):
        self.assertEqual(normalize_api_key(" polygon-key \n"), "polygon-key")


class IntradayWatchlistTierTests(unittest.TestCase):
    def test_base_watchlist_only_scans_core_names_every_cycle(self):
        self.assertEqual(BASE_WATCHLIST, list(dict.fromkeys(CORE_WATCHLIST)))
        self.assertEqual(AUTO_WATCHLIST_LIMIT, 25)
        self.assertIn("SPY", CORE_WATCHLIST)
        self.assertIn("NVDA", CORE_WATCHLIST)
        self.assertIn("RKLB", SECONDARY_WATCHLIST)
        self.assertIn("IONQ", SPEC_WATCHLIST)
        self.assertNotIn("RKLB", BASE_WATCHLIST)
        self.assertNotIn("IONQ", BASE_WATCHLIST)

    def test_deprioritized_names_are_not_in_always_scan_list(self):
        for ticker in DEPRIORITIZED_INTRADAY_OPTIONS:
            self.assertNotIn(ticker, BASE_WATCHLIST)


if __name__ == "__main__":
    unittest.main()
