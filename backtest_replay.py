import pandas as pd
from bot_enhancements import learn_from_outcomes

LOG_FILE = "stock_technical_alerts.csv"
OUTCOME_FILE = "alert_outcomes.csv"


def replay():
    print("\n===== BACKTEST REPLAY =====\n")
    try:
        df = pd.read_csv(LOG_FILE)
    except Exception as e:
        print(f"Failed to read {LOG_FILE}: {e}")
        return

    for _, row in df.iterrows():
        print(f"{row.get('ticker')} | {row.get('entry_mode')} | RR={row.get('risk_reward')} | AI={row.get('ai_verdict')}")


def learn():
    print("\n===== ADAPTIVE LEARNING =====\n")
    try:
        df = pd.read_csv(OUTCOME_FILE)
    except Exception as e:
        print(f"Failed to read {OUTCOME_FILE}: {e}")
        return

    outcomes = df.to_dict(orient="records")
    weights = learn_from_outcomes(outcomes)
    print("Updated adaptive weights:", weights)


if __name__ == "__main__":
    replay()
    learn()
