import asyncio
from playwright.async_api import async_playwright
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def capture_chart(symbol: str, filename: str = "chart.png"):
    url = f"https://www.tradingview.com/chart/?symbol={symbol}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)
        await page.wait_for_timeout(5000)
        await page.screenshot(path=filename)
        await browser.close()

    return filename


async def analyze_chart_ai(symbol: str):
    image_path = await capture_chart(symbol)

    with open(image_path, "rb") as f:
        img = f.read()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Analyze this stock chart for swing trade: {symbol}. Identify breakout, trend, and entry."},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,"}}
                ]
            }
        ]
    )

    return response.choices[0].message.content
