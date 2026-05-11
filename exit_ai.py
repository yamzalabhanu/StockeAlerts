import os
from openai import OpenAI
from openai_models import chat_completion_options

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def option_exit_ai(symbol: str, trade: dict, current_context: dict) -> str:
    """Ask AI for exit guidance on an open option trade."""
    prompt = f"""
You are reviewing an open options swing trade.

Symbol: {symbol}
Trade: {trade}
Current context: {current_context}

Return exactly:
Decision: HOLD / TRIM / SCALE / EXIT
Reason: one short paragraph that weighs trend continuation, volume, regime, exhaustion, and projection decay
Risk: LOW / MEDIUM / HIGH
"""

    response = client.chat.completions.create(
        **chat_completion_options(
            setup=trade,
            messages=[{"role": "user", "content": prompt}],
        ),
    )
    return response.choices[0].message.content
