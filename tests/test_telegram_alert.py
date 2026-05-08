import unittest
from unittest.mock import patch

import telegram_alert


class Response:
    def __init__(self, ok, status_code=200, text=""):
        self.ok = ok
        self.status_code = status_code
        self.text = text


class TelegramAlertTests(unittest.TestCase):
    def test_send_telegram_falls_back_to_plain_text_when_markdown_fails(self):
        responses = [
            Response(False, 400, "can't parse entities"),
            Response(True, 200, "OK"),
        ]

        with patch.object(telegram_alert, "TOKEN", "token"), \
            patch.object(telegram_alert, "CHAT_ID", "chat"), \
            patch("telegram_alert.requests.post", side_effect=responses) as post:
            sent = telegram_alert.send_telegram("*broken markdown")

        self.assertTrue(sent)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].kwargs["data"]["parse_mode"], "Markdown")
        self.assertNotIn("parse_mode", post.call_args_list[1].kwargs["data"])

    def test_send_telegram_returns_false_when_not_configured(self):
        with patch.object(telegram_alert, "TOKEN", ""), \
            patch.object(telegram_alert, "CHAT_ID", ""):
            self.assertFalse(telegram_alert.send_telegram("message"))


if __name__ == "__main__":
    unittest.main()
