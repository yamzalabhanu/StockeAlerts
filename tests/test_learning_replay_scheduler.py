import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from learning_replay_scheduler import (
    check_and_run,
    changed_model_files,
    fingerprint_models,
    maybe_run_after_learning_change,
    should_run_replay,
)


class LearningReplaySchedulerTests(unittest.TestCase):
    def test_detects_model_fingerprint_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "ml_setup_model.json"
            model_path.write_text('{"A": 1}', encoding="utf-8")
            first = fingerprint_models([str(model_path)])

            model_path.write_text('{"A": 2}', encoding="utf-8")
            second = fingerprint_models([str(model_path)])

        self.assertEqual(changed_model_files(first, first), [])
        self.assertEqual(changed_model_files(second, first), [str(model_path)])

    def test_changed_model_runs_only_after_minimum_interval(self):
        now = dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.timezone.utc)
        current = {"model.json": {"sha256": "new"}}
        state = {
            "last_run_at": (now - dt.timedelta(hours=1)).isoformat(),
            "model_fingerprints": {"model.json": {"sha256": "old"}},
        }

        decision = should_run_replay(current, state, min_interval_hours=6, now=now)

        self.assertFalse(decision["run"])
        self.assertIn("minimum interval", decision["reason"])
        self.assertEqual(decision["changed_files"], ["model.json"])

    def test_check_and_run_persists_state_after_periodic_replay(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "setup_performance_learning.json"
            state_path = Path(tmpdir) / "state.json"
            model_path.write_text(json.dumps({"buckets": {"ALL": {"wins": 1}}}), encoding="utf-8")

            with patch("learning_replay_scheduler.run_jobs", return_value=[{"job": "replay", "status": "completed"}]) as run_jobs:
                result = check_and_run(
                    model_files=[str(model_path)],
                    state_file=str(state_path),
                    min_interval_hours=6,
                    jobs=["replay"],
                    now=dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.timezone.utc),
                )

            saved = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertTrue(result["run"])
        self.assertEqual(result["reason"], "learning model changed")
        self.assertEqual(result["jobs"], [{"job": "replay", "status": "completed"}])
        self.assertIn(str(model_path), saved["model_fingerprints"])
        run_jobs.assert_called_once()

    def test_auto_hook_is_opt_in(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(maybe_run_after_learning_change(model_files=["missing.json"]))


if __name__ == "__main__":
    unittest.main()
