import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Trading Bot Dashboard", layout="wide")

LOG_FILE = "stock_technical_alerts.csv"

st.title("📊 Trading Bot Performance Dashboard")

try:
    df = pd.read_csv(LOG_FILE)
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

st.subheader("Overview")
st.write(df.tail(10))

col1, col2 = st.columns(2)

with col1:
    st.subheader("Entry Mode Distribution")
    if "entry_mode" in df:
        fig = px.histogram(df, x="entry_mode")
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Risk Reward Distribution")
    if "risk_reward" in df:
        fig = px.histogram(df, x="risk_reward")
        st.plotly_chart(fig, use_container_width=True)

st.subheader("Average Metrics")
st.write({
    "Average RR": df.get("risk_reward", pd.Series()).mean(),
    "Total Trades": len(df)
})
