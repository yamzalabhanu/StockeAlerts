import csv
import streamlit as st
import pandas as pd
import plotly.express as px
from daily_report_engine import probability_calibration_summary

st.set_page_config(page_title="Trading Bot Dashboard", layout="wide")

LOG_FILE = "stock_technical_alerts.csv"
CLEAN_LOG_FILE = "stock_technical_alerts.cleaned.csv"


def read_csv_robust(path):
    """Read dashboard CSV even when old rows have a different schema."""
    try:
        return pd.read_csv(path), None
    except Exception as first_error:
        try:
            df = pd.read_csv(
                path,
                engine="python",
                on_bad_lines="skip",
                quoting=csv.QUOTE_MINIMAL,
            )
            df.to_csv(CLEAN_LOG_FILE, index=False)
            return df, str(first_error)
        except Exception as second_error:
            raise RuntimeError(f"Standard read failed: {first_error}; robust read failed: {second_error}")


st.title("📊 Trading Bot Performance Dashboard")

try:
    df, warning = read_csv_robust(LOG_FILE)
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

if warning:
    st.warning(
        "Original CSV has malformed/mixed-schema rows. Dashboard skipped bad rows and wrote "
        f"a clean copy to `{CLEAN_LOG_FILE}`. Original error: {warning}"
    )

if df.empty:
    st.info("No trade rows found yet. Run `python main.py` during market hours to generate alerts.")
    st.stop()

st.subheader("Recent Trades")
st.dataframe(df.tail(25), use_container_width=True)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Trades", len(df))
with col2:
    avg_rr = pd.to_numeric(df.get("risk_reward", pd.Series(dtype=float)), errors="coerce").mean()
    st.metric("Average R/R", round(avg_rr, 2) if pd.notna(avg_rr) else "N/A")
with col3:
    avg_score = pd.to_numeric(df.get("score", pd.Series(dtype=float)), errors="coerce").mean()
    st.metric("Average Score", round(avg_score, 1) if pd.notna(avg_score) else "N/A")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Entry Mode Distribution")
    if "entry_mode" in df:
        fig = px.histogram(df, x="entry_mode")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No `entry_mode` column found yet.")

with col2:
    st.subheader("Risk/Reward Distribution")
    if "risk_reward" in df:
        rr_df = df.copy()
        rr_df["risk_reward"] = pd.to_numeric(rr_df["risk_reward"], errors="coerce")
        fig = px.histogram(rr_df.dropna(subset=["risk_reward"]), x="risk_reward")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No `risk_reward` column found yet.")

st.subheader("Setup Quality")
if "setup_quality" in df:
    st.bar_chart(df["setup_quality"].value_counts())


st.subheader("Probability Calibration")
try:
    calibration = probability_calibration_summary()
    if calibration.get("samples"):
        st.metric(
            "Probability MAE",
            round(float(calibration.get("mean_absolute_error") or 0), 3),
            help="Mean absolute error between predicted win probability and closed outcome.",
        )
        cal_df = pd.DataFrame(calibration.get("buckets", []))
        st.dataframe(cal_df, use_container_width=True)
        non_empty = cal_df[cal_df["samples"] > 0] if not cal_df.empty and "samples" in cal_df else cal_df
        if not non_empty.empty:
            fig = px.bar(
                non_empty,
                x="label",
                y=["avg_predicted_probability", "realized_win_rate"],
                barmode="group",
                title="Predicted vs Realized Win Rate by Probability Bucket",
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No closed probability samples available yet.")
except Exception as e:
    st.warning(f"Probability calibration unavailable: {e}")


st.subheader("Raw Data")
st.dataframe(df, use_container_width=True)
