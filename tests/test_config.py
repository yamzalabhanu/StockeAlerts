import unittest

from config import normalize_api_key


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


if __name__ == "__main__":
    unittest.main()
