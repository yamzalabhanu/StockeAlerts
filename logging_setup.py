import builtins
import datetime as dt


_ORIGINAL_PRINT = builtins.print
_TIMESTAMP_PRINT_ENABLED = False


def enable_timestamped_prints() -> None:
    """Prefix standard print output with UTC timestamps."""
    global _TIMESTAMP_PRINT_ENABLED
    if _TIMESTAMP_PRINT_ENABLED:
        return

    def _timestamped_print(*args, **kwargs):
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        _ORIGINAL_PRINT(f"[{timestamp}]", *args, **kwargs)

    builtins.print = _timestamped_print
    _TIMESTAMP_PRINT_ENABLED = True

