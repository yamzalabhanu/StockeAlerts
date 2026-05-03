import base64
import os
from pathlib import Path
from openai import OpenAI
from playwright.async_api import async_playwright

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CHART_DIR = Path("charts")
CHART_DIR.mkdir(exist_ok=True)


async def capture_chart(symbol: str, timeframe: str = "D") -> str:
    """Capture a TradingView chart screenshot for visual confirmation."""
    clean_symbol = symbol.replace(":", "_").replace("/", "_")
    filename = CHART_DIR / f"{clean_symbol}_{timeframe}.png"
    url = f"https://www.tradingview.com/chart/?symbol={symbol}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(7000)
        await page.screenshot(path=str(filename), full_page=True)
        await browser.close()

    return str(filename)


async def analyze_chart_ai(symbol: str, analysis: dict | None = None) -> str:
    """Send TradingView chart screenshot to OpenAI Vision for setup confirmation."""
    image_path = await capture_chart(symbol)

    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    context = f"Technical data: {analysis}" if analysis else "No structured technical data provided."

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Analyze this 6-month TradingView-style chart for {symbol}. "
                            f"{context}\n"
                            "Return a concise swing-trade decision with exactly these fields:\n"
                            "Decision: ENTER / WAIT / AVOID\n"
                            "Trend: bullish / bearish / sideways\n"
                            "Pattern: breakout / breakdown / base / chop / extended\n"
                            "Entry: exact trigger or retest area\n"
                            "Stop: invalidation level\n"
                            "Risk: low / medium / high\n"
                            "Reason: one short paragraph."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"},
                    },
                ],
            }
        ],
    )

    return response.choices[0].message.content
