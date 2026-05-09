from openai import OpenAI
import os
from openai_models import chat_completion_options

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def ai_decision(symbol, analysis):
    prompt = f"""
    Analyze this stock for swing trade:

    Symbol: {symbol}
    Signal: {analysis['signal']}
    Price: {analysis['price']}
    EMA8: {analysis['ema8']}
    EMA21: {analysis['ema21']}
    EMA50: {analysis['ema50']}
    Volume Strength: {analysis['rel_volume']}

    Give decision:
    - ENTER / WAIT / AVOID
    - Reason
    - Risk level
    """

    response = client.chat.completions.create(
        **chat_completion_options(
            messages=[{"role": "user", "content": prompt}]
        )
    )

    return response.choices[0].message.content
