import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import option_order_manager as manager


class OptionOrderManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "state.json"
        self.telegram_messages = []

    def tearDown(self):
        self.tmpdir.cleanup()

    def send_telegram(self, message):
        self.telegram_messages.append(message)
        return True

    @patch("option_order_manager.broker.PAPER", True)
    @patch("option_order_manager.broker.place_option_limit_order", return_value="buy-order-123")
    def test_buys_recommended_option_in_paper_mode_and_sends_confirmation(self, place_order):
        position = manager.maybe_buy_recommended_option(
            ticker="SPY",
            direction="CALL",
            option_contract={
                "status": "OK",
                "contract_symbol": "SPY260515C00500000",
                "ask": 2.5,
                "mid": 2.4,
            },
            telegram_sender=self.send_telegram,
            state_path=self.state_path,
        )

        self.assertIsNotNone(position)
        place_order.assert_called_once_with("SPY260515C00500000", 1, "BUY", 2.5)
        self.assertTrue(any("Alpaca paper BUY submitted" in msg for msg in self.telegram_messages))
        self.assertTrue(any("take profit +20% / stop -10%" in msg for msg in self.telegram_messages))

    @patch("option_order_manager.broker.PAPER", True)
    @patch("option_order_manager.broker.place_option_limit_order", return_value="sell-order-123")
    def test_sells_open_option_at_profit_target_and_sends_confirmation(self, place_order):
        manager.maybe_buy_recommended_option(
            ticker="SPY",
            direction="CALL",
            option_contract={"status": "OK", "contract_symbol": "SPY260515C00500000", "ask": 2.0},
            telegram_sender=self.send_telegram,
            state_path=self.state_path,
        )
        place_order.reset_mock()
        self.telegram_messages.clear()

        closed = manager.manage_open_option_positions(
            telegram_sender=self.send_telegram,
            state_path=self.state_path,
            price_lookup={"SPY260515C00500000": 2.42},
        )

        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["exit_reason"], "TAKE_PROFIT")
        place_order.assert_called_once_with("SPY260515C00500000", 1, "SELL", 2.42)
        self.assertTrue(any("Alpaca paper SELL submitted" in msg for msg in self.telegram_messages))
        self.assertTrue(any("P/L: +21.00%" in msg for msg in self.telegram_messages))

    @patch("option_order_manager.broker.PAPER", True)
    @patch("option_order_manager.broker.place_option_limit_order", return_value="sell-order-456")
    def test_sells_open_option_at_stop_loss(self, place_order):
        manager.maybe_buy_recommended_option(
            ticker="QQQ",
            direction="PUT",
            option_contract={"status": "OK", "contract_symbol": "QQQ260515P00450000", "ask": 3.0},
            telegram_sender=self.send_telegram,
            state_path=self.state_path,
        )
        place_order.reset_mock()

        closed = manager.manage_open_option_positions(
            telegram_sender=self.send_telegram,
            state_path=self.state_path,
            price_lookup={"QQQ260515P00450000": 2.69},
        )

        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["exit_reason"], "STOP_LOSS")
        place_order.assert_called_once_with("QQQ260515P00450000", 1, "SELL", 2.69)

    @patch("option_order_manager.broker.PAPER", False)
    @patch("option_order_manager.broker.place_option_limit_order")
    def test_blocks_buy_when_alpaca_is_not_paper(self, place_order):
        position = manager.maybe_buy_recommended_option(
            ticker="SPY",
            direction="CALL",
            option_contract={"status": "OK", "contract_symbol": "SPY260515C00500000", "ask": 2.5},
            telegram_sender=self.send_telegram,
            state_path=self.state_path,
        )

        self.assertIsNone(position)
        place_order.assert_not_called()
        self.assertTrue(any("blocked non-paper Alpaca execution" in msg for msg in self.telegram_messages))


if __name__ == "__main__":
    unittest.main()
