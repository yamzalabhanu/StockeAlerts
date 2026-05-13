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
        state = manager._load_state(self.state_path)
        tracked = state["positions"]["SPY260515C00500000"]
        self.assertEqual(tracked["submitted_price"], 2.5)
        self.assertTrue(any("Submitted price tracked: $2.50" in msg for msg in self.telegram_messages))
        self.assertTrue(any("check every 5 min; take profit +20% / stop -10%" in msg for msg in self.telegram_messages))

    @patch("option_order_manager.broker.PAPER", True)
    @patch("option_order_manager.broker.place_option_limit_order", return_value="buy-order-456")
    def test_strips_polygon_option_prefix_before_buying(self, place_order):
        position = manager.maybe_buy_recommended_option(
            ticker="GLD",
            direction="CALL",
            option_contract={
                "status": "OK",
                "contract_symbol": "O:GLD260515C00457000",
                "ask": 0.26,
            },
            telegram_sender=self.send_telegram,
            state_path=self.state_path,
        )

        self.assertIsNotNone(position)
        self.assertEqual(position.contract_symbol, "GLD260515C00457000")
        place_order.assert_called_once_with("GLD260515C00457000", 1, "BUY", 0.26)
        self.assertTrue(any("Contract: GLD260515C00457000" in msg for msg in self.telegram_messages))

    @patch("option_order_manager.broker.PAPER", True)
    @patch(
        "option_order_manager.broker.place_option_limit_order",
        return_value='Option order failed: {"code":42210000,"message":"asset not found"}',
    )
    def test_does_not_track_or_confirm_failed_option_buy(self, place_order):
        position = manager.maybe_buy_recommended_option(
            ticker="GLD",
            direction="CALL",
            option_contract={"status": "OK", "contract_symbol": "O:GLD260515C00457000", "ask": 0.26},
            telegram_sender=self.send_telegram,
            state_path=self.state_path,
        )

        self.assertIsNone(position)
        place_order.assert_called_once_with("GLD260515C00457000", 1, "BUY", 0.26)
        state = manager._load_state(self.state_path)
        self.assertEqual(state["positions"], {})
        self.assertTrue(any("Alpaca paper BUY failed" in msg for msg in self.telegram_messages))
        self.assertFalse(any("Alpaca paper BUY submitted" in msg for msg in self.telegram_messages))

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
        self.assertEqual(closed[0]["current_premium"], 2.42)
        self.assertEqual(closed[0]["last_pnl_pct"], 21.0)
        self.assertIsNotNone(closed[0]["last_checked_at"])
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

    @patch("option_order_manager.broker.PAPER", True)
    @patch("option_order_manager.broker.place_option_limit_order", return_value="sell-order-789")
    def test_sells_legacy_polygon_prefixed_state_with_alpaca_symbol(self, place_order):
        state = {
            "positions": {
                "O:GLD260515C00457000": {
                    "ticker": "GLD",
                    "direction": "CALL",
                    "contract_symbol": "O:GLD260515C00457000",
                    "qty": 1,
                    "entry_premium": 0.26,
                    "status": "OPEN",
                    "opened_at": "2026-05-12T00:00:00+00:00",
                }
            }
        }
        manager._save_state(state, self.state_path)

        closed = manager.manage_open_option_positions(
            telegram_sender=self.send_telegram,
            state_path=self.state_path,
            price_lookup={"GLD260515C00457000": 0.32},
        )

        self.assertEqual(len(closed), 1)
        place_order.assert_called_once_with("GLD260515C00457000", 1, "SELL", 0.32)

    @patch("option_order_manager.broker.PAPER", True)
    @patch(
        "option_order_manager.broker.place_option_limit_order",
        side_effect=["buy-order-999", "Option order failed: insufficient qty"],
    )
    def test_keeps_position_open_when_managed_sell_fails(self, place_order):
        manager.maybe_buy_recommended_option(
            ticker="IWM",
            direction="CALL",
            option_contract={"status": "OK", "contract_symbol": "IWM260515C00200000", "ask": 1.0},
            telegram_sender=self.send_telegram,
            state_path=self.state_path,
        )
        self.telegram_messages.clear()

        closed = manager.manage_open_option_positions(
            telegram_sender=self.send_telegram,
            state_path=self.state_path,
            price_lookup={"IWM260515C00200000": 1.21},
        )

        self.assertEqual(closed, [])
        self.assertEqual(place_order.call_count, 2)
        state = manager._load_state(self.state_path)
        tracked = state["positions"]["IWM260515C00200000"]
        self.assertEqual(tracked["status"], "OPEN")
        self.assertEqual(tracked["current_premium"], 1.21)
        self.assertEqual(tracked["last_pnl_pct"], 21.0)
        self.assertTrue(any("SELL failed; position remains tracked as OPEN" in msg for msg in self.telegram_messages))

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
