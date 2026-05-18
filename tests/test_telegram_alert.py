import unittest
from unittest.mock import patch

import telegram_alert
from telegram_formatting import telegram_html_from_markdown


class Response:
    def __init__(self, ok, status_code=200, text=""):
        self.ok = ok
        self.status_code = status_code
        self.text = text


class TelegramAlertTests(unittest.TestCase):
    def test_send_telegram_falls_back_to_plain_text_when_formatted_send_fails(self):
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
        self.assertEqual(post.call_args_list[0].kwargs["data"]["parse_mode"], "HTML")
        self.assertNotIn("parse_mode", post.call_args_list[1].kwargs["data"])

    def test_send_telegram_uses_safe_html_payload_for_dynamic_alert_text(self):
        with patch.object(telegram_alert, "TOKEN", "token"), \
            patch.object(telegram_alert, "CHAT_ID", "chat"), \
            patch("telegram_alert.requests.post", return_value=Response(True)) as post:
            sent = telegram_alert.send_telegram("*A+ SETUP:* TEST_KEY & <risk> *")

        self.assertTrue(sent)
        payload = post.call_args.kwargs["data"]
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertEqual(
            payload["text"],
            "<b>A+ SETUP:</b> TEST_KEY &amp; &lt;risk&gt; *",
        )

    def test_markdown_like_bold_is_converted_after_html_escaping(self):
        self.assertEqual(
            telegram_html_from_markdown("⭐ *AI Score:* ticker A_B & setup"),
            "⭐ <b>AI Score:</b> ticker A_B &amp; setup",
        )

    def test_send_telegram_splits_messages_that_exceed_telegram_limit(self):
        long_message = "Header\n" + ("line of alert detail\n" * 220)

        with patch.object(telegram_alert, "TOKEN", "token"), \
            patch.object(telegram_alert, "CHAT_ID", "chat"), \
            patch("telegram_alert.requests.post", return_value=Response(True)) as post:
            sent = telegram_alert.send_telegram(long_message)

        self.assertTrue(sent)
        self.assertGreater(post.call_count, 1)
        for call in post.call_args_list:
            payload = call.kwargs["data"]
            self.assertLessEqual(
                len(payload["text"]),
                telegram_alert.TELEGRAM_MESSAGE_LIMIT,
            )

    def test_send_telegram_splits_by_formatted_payload_length(self):
        long_message = "Header\n" + ("A&B <risk> detail line\n" * 260)

        with patch.object(telegram_alert, "TOKEN", "token"), \
            patch.object(telegram_alert, "CHAT_ID", "chat"), \
            patch("telegram_alert.requests.post", return_value=Response(True)) as post:
            sent = telegram_alert.send_telegram(long_message)

        self.assertTrue(sent)
        self.assertGreater(post.call_count, 1)
        for call in post.call_args_list:
            payload = call.kwargs["data"]
            self.assertLessEqual(
                len(payload["text"]),
                telegram_alert.TELEGRAM_MESSAGE_LIMIT,
            )

    def test_send_telegram_message_accepts_explicit_bot_credentials(self):
        with patch("telegram_alert.requests.post", return_value=Response(True)) as post:
            sent = telegram_alert.send_telegram_message(
                "bot alert", "bot-token", "bot-chat"
            )

        self.assertTrue(sent)
        self.assertEqual(post.call_args.kwargs["data"]["chat_id"], "bot-chat")

    def test_send_telegram_returns_false_when_any_chunk_fails(self):
        long_message = "Header\n" + ("line of alert detail\n" * 220)
        responses = [
            Response(True, 200, "OK"),
            Response(False, 400, "message is too long"),
            Response(False, 400, "message is too long"),
        ]

        with patch.object(telegram_alert, "TOKEN", "token"), \
            patch.object(telegram_alert, "CHAT_ID", "chat"), \
            patch("telegram_alert.requests.post", side_effect=responses) as post:
            sent = telegram_alert.send_telegram(long_message)

        self.assertFalse(sent)
        self.assertEqual(post.call_count, 3)

    def test_send_telegram_returns_false_when_not_configured(self):
        with patch.object(telegram_alert, "TOKEN", ""), \
            patch.object(telegram_alert, "CHAT_ID", ""):
            self.assertFalse(telegram_alert.send_telegram("message"))


if __name__ == "__main__":
    unittest.main()
