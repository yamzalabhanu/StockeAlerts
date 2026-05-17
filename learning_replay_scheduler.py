"""Periodic replay/backtest automation for learning-model changes.

The scheduler is intentionally lightweight and deterministic: it fingerprints the
learning model files, stores the last replay state on disk, and only runs replay
jobs when a model changed and the minimum interval has elapsed (unless forced).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

DEFAULT_MODEL_FILES = (
    "ml_setup_model.json",
    "setup_performance_learning.json",
    "projection_learning.json",
)
DEFAULT_STATE_FILE = ".learning_replay_state.json"
DEFAULT_MIN_INTERVAL_HOURS = 6.0
ENV_ENABLED = "LEARNING_REPLAY_AUTORUN"
ENV_MIN_INTERVAL_HOURS = "LEARNING_REPLAY_MIN_INTERVAL_HOURS"
ENV_STATE_FILE = "LEARNING_REPLAY_STATE_FILE"
ENV_MODEL_FILES = "LEARNING_REPLAY_MODEL_FILES"
ENV_JOBS = "LEARNING_REPLAY_JOBS"
ENV_SYMBOLS = "LEARNING_REPLAY_SYMBOLS"

ReplayJob = Callable[[], Any]


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_timestamp(value: Any) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def env_model_files() -> List[str]:
    raw = os.getenv(ENV_MODEL_FILES, "")
    if not raw.strip():
        return list(DEFAULT_MODEL_FILES)
    return [part.strip() for part in raw.split(",") if part.strip()]


def fingerprint_file(path: str) -> Optional[Dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None

    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    stat = file_path.stat()
    return {
        "sha256": digest.hexdigest(),
        "size": stat.st_size,
        "mtime": dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc).isoformat(),
    }


def fingerprint_models(model_files: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    fingerprints: Dict[str, Dict[str, Any]] = {}
    for path in model_files:
        fingerprint = fingerprint_file(path)
        if fingerprint:
            fingerprints[str(path)] = fingerprint
    return fingerprints


def load_state(path: str = DEFAULT_STATE_FILE) -> Dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return {}
    try:
        with state_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def save_state(state: Dict[str, Any], path: str = DEFAULT_STATE_FILE) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)


def changed_model_files(
    current: Dict[str, Dict[str, Any]], previous: Optional[Dict[str, Dict[str, Any]]]
) -> List[str]:
    previous = previous or {}
    changed = []
    for path, fingerprint in current.items():
        if previous.get(path, {}).get("sha256") != fingerprint.get("sha256"):
            changed.append(path)
    return changed


def should_run_replay(
    current_fingerprints: Dict[str, Dict[str, Any]],
    state: Optional[Dict[str, Any]] = None,
    *,
    min_interval_hours: float = DEFAULT_MIN_INTERVAL_HOURS,
    now: Optional[dt.datetime] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Return a run decision with a human-readable reason."""
    state = state or {}
    now = now or _utc_now()
    changed = changed_model_files(current_fingerprints, state.get("model_fingerprints"))

    if not current_fingerprints:
        return {"run": False, "reason": "no learning model files found", "changed_files": []}

    if force:
        return {"run": True, "reason": "forced replay", "changed_files": changed or list(current_fingerprints)}

    if not changed:
        return {"run": False, "reason": "learning models unchanged", "changed_files": []}

    last_run_at = _parse_timestamp(state.get("last_run_at"))
    if last_run_at:
        elapsed_hours = (now - last_run_at).total_seconds() / 3600.0
        if elapsed_hours < max(0.0, min_interval_hours):
            return {
                "run": False,
                "reason": f"minimum interval not reached ({elapsed_hours:.2f}h/{min_interval_hours:.2f}h)",
                "changed_files": changed,
            }

    return {"run": True, "reason": "learning model changed", "changed_files": changed}


def _replay_job() -> Dict[str, Any]:
    from backtest_replay import learn, replay

    replay()
    learn()
    return {"job": "replay", "status": "completed"}


def _stock_backtest_job(symbols: Iterable[str]) -> Dict[str, Any]:
    from backtest import backtest

    results = {}
    for symbol in symbols:
        results[symbol] = backtest(symbol)
    return {"job": "stock_backtest", "symbols": list(results), "result_counts": {k: len(v) for k, v in results.items()}}


def _options_backtest_job(symbols: Iterable[str]) -> Dict[str, Any]:
    from options_backtest import backtest_options

    results = {}
    for symbol in symbols:
        results[symbol] = backtest_options(symbol)
    return {"job": "options_backtest", "symbols": list(results), "result_counts": {k: len(v) for k, v in results.items()}}


def configured_jobs() -> List[str]:
    raw = os.getenv(ENV_JOBS, "replay")
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def configured_symbols() -> List[str]:
    raw = os.getenv(ENV_SYMBOLS, "NVDA")
    return [part.strip().upper() for part in raw.split(",") if part.strip()]


def run_jobs(jobs: Optional[Iterable[str]] = None, symbols: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    selected_jobs = list(jobs or configured_jobs())
    selected_symbols = list(symbols or configured_symbols())
    results: List[Dict[str, Any]] = []

    for job in selected_jobs:
        if job == "replay":
            results.append(_replay_job())
        elif job in {"stock", "stock_backtest", "backtest"}:
            results.append(_stock_backtest_job(selected_symbols))
        elif job in {"options", "options_backtest"}:
            results.append(_options_backtest_job(selected_symbols))
        else:
            results.append({"job": job, "status": "skipped", "reason": "unknown job"})

    return results


def check_and_run(
    *,
    model_files: Optional[Iterable[str]] = None,
    state_file: Optional[str] = None,
    min_interval_hours: Optional[float] = None,
    force: bool = False,
    jobs: Optional[Iterable[str]] = None,
    symbols: Optional[Iterable[str]] = None,
    now: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    state_path = state_file or os.getenv(ENV_STATE_FILE, DEFAULT_STATE_FILE)
    interval = (
        DEFAULT_MIN_INTERVAL_HOURS
        if min_interval_hours is None
        else float(min_interval_hours)
    )
    if min_interval_hours is None:
        interval = _safe_float(os.getenv(ENV_MIN_INTERVAL_HOURS), DEFAULT_MIN_INTERVAL_HOURS)

    current = fingerprint_models(model_files or env_model_files())
    state = load_state(state_path)
    decision = should_run_replay(current, state, min_interval_hours=interval, now=now, force=force)
    run_at = now or _utc_now()

    if not decision["run"]:
        state["last_checked_at"] = run_at.isoformat()
        state["model_fingerprints"] = current
        save_state(state, state_path)
        return {**decision, "state_file": state_path, "jobs": []}

    job_results = run_jobs(jobs=jobs, symbols=symbols)
    state.update(
        {
            "last_checked_at": run_at.isoformat(),
            "last_run_at": run_at.isoformat(),
            "last_reason": decision["reason"],
            "last_changed_files": decision["changed_files"],
            "last_jobs": job_results,
            "model_fingerprints": current,
        }
    )
    save_state(state, state_path)
    return {**decision, "state_file": state_path, "jobs": job_results}


def maybe_run_after_learning_change(model_files: Optional[Iterable[str]] = None) -> Optional[Dict[str, Any]]:
    """Opt-in hook for model writers.

    Set LEARNING_REPLAY_AUTORUN=true to have learning saves trigger the periodic
    replay check. The interval/state file still prevents repeated heavy work.
    """
    if not env_flag(ENV_ENABLED, default=False):
        return None
    return check_and_run(model_files=model_files)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run replay/backtest jobs when learning models change.")
    parser.add_argument("--force", action="store_true", help="Run jobs even when model fingerprints did not change.")
    parser.add_argument("--state-file", default=os.getenv(ENV_STATE_FILE, DEFAULT_STATE_FILE))
    parser.add_argument("--min-interval-hours", type=float, default=_safe_float(os.getenv(ENV_MIN_INTERVAL_HOURS), DEFAULT_MIN_INTERVAL_HOURS))
    parser.add_argument("--model-file", action="append", dest="model_files", help="Learning model file to fingerprint; may be repeated.")
    parser.add_argument("--jobs", default=os.getenv(ENV_JOBS, "replay"), help="Comma-separated jobs: replay, stock_backtest, options_backtest.")
    parser.add_argument("--symbols", default=os.getenv(ENV_SYMBOLS, "NVDA"), help="Comma-separated symbols for backtest jobs.")
    args = parser.parse_args(argv)

    jobs = [part.strip() for part in args.jobs.split(",") if part.strip()]
    symbols = [part.strip().upper() for part in args.symbols.split(",") if part.strip()]
    result = check_and_run(
        model_files=args.model_files or env_model_files(),
        state_file=args.state_file,
        min_interval_hours=args.min_interval_hours,
        force=args.force,
        jobs=jobs,
        symbols=symbols,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
