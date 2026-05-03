from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def ai_score_setup(ticker, tech, setup):
    if not client:
        return setup.get("score", 0)

    prompt = f"""
Score this trading setup from 0 to 100.

Ticker: {ticker}
Price: {tech['price']}
VWAP: {tech['vwap']}
EMA: {tech['ema9']}, {tech['ema21']}, {tech['ema50']}
Trend: {tech['trend_5m']} / {tech['trend_15m']}
Reasons: {setup.get('reasons')}

Return ONLY a number.
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        return int(res.choices[0].message.content.strip())
    except Exception:
        return setup.get("score", 0)
