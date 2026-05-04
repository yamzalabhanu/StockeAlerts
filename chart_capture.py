from playwright.async_api import async_playwright
from symbol_utils import tradingview_symbol, normalize_symbol, is_valid_symbol


async def capture_chart(ticker, filename="chart.png"):
    symbol_clean = normalize_symbol(ticker)

    if not is_valid_symbol(symbol_clean):
        raise ValueError(f"Invalid symbol for chart capture: {ticker}")

    symbol = tradingview_symbol(symbol_clean)
    url = f"https://www.tradingview.com/chart/?symbol={symbol}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})

        await page.goto(url, timeout=60000)
        await page.wait_for_timeout(8000)

        await page.screenshot(path=filename, full_page=False)

        await browser.close()

    return filename
