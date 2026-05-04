import csv
import os
import pandas as pd
from bot_enhancements import learn_from_outcomes

LOG_FILE = "stock_technical_alerts.csv"
OUTCOME_FILE = "alert_outcomes.csv"
CLEAN_LOG_FILE = "stock_technical_alerts.cleaned.csv"


def read_csv_robust(path):
    """Read CSV logs even when older rows have mismatched column counts.

    The bot schema changed over time, so old local CSV files may contain rows with
    extra fields. This reader skips malformed rows instead of crashing replay.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    try:
        return pd.read_csv(path)
    except Exception as first_error:
        print(f"Standard CSV read failed for {path}: {first_error}")
        print("Retrying with python engine and skipping malformed rows...")

    return pd.read_csv(
        path,
        engine="python",
        on_bad_lines="skip",
        quoting=csv.QUOTE_MINIMAL,
    )


def write_clean_copy(df, output_path=CLEAN_LOG_FILE):
    df.to_csv(output_path, index=False)
    print(f"Cleaned replay-compatible copy written to: {output_path}")


def replay():
    print("\n===== BACKTEST REPLAY =====\n")
    try:
        df = read_csv_robust(LOG_FILE)
    except Exception as e:
        print(f"Failed to read {LOG_FILE}: {e}")
        return

    if df.empty:
        print("No replay rows found.")
        return

    write_clean_copy(df)

    for _, row in df.iterrows():
        print(
            f"{row.get('ticker')} | "
            f"{row.get('entry_mode', 'UNKNOWN')} | "
            f"RR={row.get('risk_reward')} | "
            f"AI={row.get('ai_verdict')} | "
            f"Score={row.get('score')}"
        )

    print(f"\nReplay rows processed: {len(df)}")


def learn():
    print("\n===== ADAPTIVE LEARNING =====\n")
    try:
        df = read_csv_robust(OUTCOME_FILE)
    except Exception as e:
        print(f"Failed to read {OUTCOME_FILE}: {e}")
        return

    if df.empty:
        print("No outcome rows found.")
        return

    outcomes = df.to_dict(orient="records")
    weights = learn_from_outcomes(outcomes)
    print("Updated adaptive weights:", weights)


if __name__ == "__main__":
    replay()
    learn()
