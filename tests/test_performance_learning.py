import tempfile
import unittest
from pathlib import Path

from outcome_schema import OUTCOME_FIELDS, append_outcome_row, read_outcome_rows
from performance_learning import DEFAULT_FORECAST_ACCURACY, DEFAULT_WIN_RATE, build_learning_model, get_setup_learning
from swing_scanner import format_swing_alert


class OutcomeCsvSchemaTests(unittest.TestCase):
    def test_reads_mixed_schema_outcomes_without_dropping_new_rows(self):
        old_header = [
            "timestamp",
            "ticker",
            "direction",
            "entry",
            "stop",
            "target",
            "result",
            "target_hit",
            "stop_hit",
            "target_time",
            "stop_time",
            "max_gain_pct",
            "max_loss_pct",
        ]
        new_row = [
            "2026-05-11T14:00:00+00:00",
            "MSFT",
            "PUT",
            "200",
            "210",
            "180",
            "SWING",
            "BREAKOUT",
            "setup-1",
            "BEAR",
            "DOWNTREND",
            "BREAKDOWN",
            "80",
            "82",
            "91",
            "10",
            "LOSS",
            "False",
            "True",
            "",
            "2026-05-11T14:30:00+00:00",
            "2",
            "5",
            "20",
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "alert_outcomes.csv"
            path.write_text(
                ",".join(old_header)
                + "\n2026-05-11T13:00:00+00:00,AAPL,CALL,100,95,110,WIN,True,False,2026-05-11T13:15:00+00:00,,12,1\n"
                + ",".join(new_row)
                + "\n",
                encoding="utf-8",
            )

            rows = read_outcome_rows(str(path))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["result"], "WIN")
        self.assertEqual(rows[1]["alert_type"], "SWING")
        self.assertEqual(rows[1]["entry_mode"], "BREAKOUT")
        self.assertEqual(rows[1]["result"], "LOSS")

        model = build_learning_model(rows)
        self.assertEqual(model["buckets"]["ALL"]["wins"], 1)
        self.assertEqual(model["buckets"]["ALL"]["losses"], 1)

    def test_append_outcome_row_migrates_stale_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "alert_outcomes.csv"
            path.write_text(
                "timestamp,ticker,direction,entry,stop,target,result,target_hit,stop_hit,target_time,stop_time,max_gain_pct,max_loss_pct\n",
                encoding="utf-8",
            )

            append_outcome_row(
                str(path),
                {
                    "timestamp": "2026-05-11T13:00:00+00:00",
                    "ticker": "AAPL",
                    "direction": "CALL",
                    "entry_mode": "RETEST",
                    "result": "WIN",
                    "max_gain_pct": 4,
                    "forecast_accuracy_pct": 80,
                },
            )

            header = path.read_text(encoding="utf-8").splitlines()[0].split(",")

        self.assertEqual(header, OUTCOME_FIELDS)


class PerformanceLearningFallbackTests(unittest.TestCase):
    def test_missing_learning_history_uses_neutral_baseline_not_zero(self):
        learning = get_setup_learning(
            {"alert_type": "SWING", "entry_mode": "SWING", "direction": "CALL"},
            model={"buckets": {}},
        )

        self.assertEqual(learning["key"], "BASELINE")
        self.assertEqual(learning["stats"]["win_rate"], DEFAULT_WIN_RATE)
        self.assertEqual(learning["stats"]["forecast_accuracy"], DEFAULT_FORECAST_ACCURACY)

    def test_incomplete_zero_move_rows_do_not_force_zero_forecast(self):
        model = build_learning_model([
            {
                "alert_type": "SWING",
                "entry_mode": "SWING",
                "direction": "CALL",
                "entry": 100,
                "target": 110,
                "result": "OPEN_OR_BREAKEVEN",
                "max_gain_pct": 0,
                "max_loss_pct": 0,
                "forecast_accuracy_pct": 0,
            }
        ])

        self.assertEqual(model["buckets"]["ALL"]["forecast_accuracy"], DEFAULT_FORECAST_ACCURACY)
        self.assertEqual(model["buckets"]["ALL"]["forecast_accuracy_samples"], 0)

    def test_open_rows_do_not_calibrate_forecast_without_closed_outcomes(self):
        model = build_learning_model([
            {
                "alert_type": "SWING",
                "entry_mode": "SWING",
                "direction": "CALL",
                "entry": 100,
                "target": 110,
                "result": "OPEN_OR_BREAKEVEN",
                "max_gain_pct": 4,
                "max_loss_pct": 2,
                "forecast_accuracy_pct": 0,
            }
        ])

        self.assertEqual(model["buckets"]["ALL"]["forecast_accuracy"], DEFAULT_FORECAST_ACCURACY)
        self.assertEqual(model["buckets"]["ALL"]["forecast_accuracy_samples"], 0)

    def test_swing_alert_history_line_does_not_display_zero_for_missing_stats(self):
        message = format_swing_alert(
            "TEST",
            {
                "direction": "CALL",
                "tier": "A+",
                "score": 95,
                "entry": 100,
                "stop": 95,
                "target": 115,
                "risk_reward": 3,
                "hold_days": "2-10",
                "reasons": ["benchmark"],
                "ai_reasoning": {"decision": "A+", "final_score": 95},
            },
        )

        self.assertIn("WR 50.0%", message)
        self.assertIn("Forecast 50.0%", message)


if __name__ == "__main__":
    unittest.main()
