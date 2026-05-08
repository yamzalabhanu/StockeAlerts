import datetime as dt
from typing import Dict, Optional, Tuple

from bot_utils import safe_float
from config import (
    MIN_RISK_REWARD,
    SWING_A_PLUS_SCORE,
    SWING_A_SCORE,
    SWING_ATR_STOP_MULTIPLIER,
    SWING_ATR_TARGET_MULTIPLIER,
    SWING_HOLD_DAYS_MAX,
    SWING_HOLD_DAYS_MIN,
    SWING_MIN_REASONS,
    SWING_MIN_SCORE,
    SWING_PULLBACK_TOLERANCE_PCT,
)

# existing helper functions remain unchanged above...

def format_swing_alert(ticker: str, setup: Dict) -> str:
    setup = setup or {}

    emoji = "🟢" if setup.get("direction") == "CALL" else "🔴"

    probability = setup.get("ml_probability")

    reasoning = setup.get("ai_reasoning") or {}

    narrative = reasoning.get("narrative", "")

    regime = (reasoning.get("regime") or {}).get("regime", "UNKNOWN")
    mtf = (reasoning.get("mtf") or {}).get("structure", "UNKNOWN")
    execution = (reasoning.get("execution") or {}).get("quality", "UNKNOWN")
    vision = (reasoning.get("vision") or {}).get("quality", "UNKNOWN")

    prob_line = (
        f"🧠 ML Probability: {probability}\n"
        if probability is not None else ""
    )

    return (
        f"{emoji} *{setup.get('tier', 'WATCH')} SWING {setup.get('direction', 'CALL')} SETUP: {ticker}*\n"
        f"⭐ Score: {setup.get('score', 0)}/100\n"
        f"{prob_line}"
        f"⏳ Hold: {setup.get('hold_days', '?')} days\n"
        f"🎯 Entry: {setup.get('entry', '?')}\n"
        f"🛑 Stop: {setup.get('stop', '?')}\n"
        f"🚀 Target: {setup.get('target', '?')}\n"
        f"📐 RR: {setup.get('risk_reward', '?')}:1\n"
        f"📝 Reasons: {', '.join(setup.get('reasons', []))}\n"
        f"🧠 AI Decision: {reasoning.get('decision', setup.get('tier', 'WATCH'))}\n"
        f"📊 Composite Score: {reasoning.get('final_score', setup.get('score', 0))}/100\n"
        f"🌍 Regime: {regime}\n"
        f"🧭 MTF: {mtf}\n"
        f"⚡ Execution: {execution}\n"
        f"🏗️ Structure: {vision}\n"
        f"\n🧠 AI Reasoning:\n{narrative}\n"
    )
