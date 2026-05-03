import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def pre_trade_filter(symbol: str, analysis: dict, option: dict) -> str:
    """Final AI gate before sending alert to improve win rate."""
    prompt = f"""
You are a strict trading filter.

Stock analysis: {analysis}
Option data: {option}

Decide:
APPROVE or REJECT

Reject if:
- late breakout
- weak volume
- near resistance
- high IV risk
- choppy trend

Return exactly:
Decision: APPROVE / REJECT
Reason: one short sentence
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content
