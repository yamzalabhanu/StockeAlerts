from playwright.async_api import async_playwright


def tv_symbol(ticker):
    ticker = ticker.upper()

    etfs = {"SPY", "QQQ", "IWM", "SMH", "TQQQ", "SQQQ", "DIA", "ARKK"}
    nyse = {
        "BA", "JPM", "BAC", "GS", "XOM", "CVX", "OXY",
        "LLY", "NVO", "PLTR", "UBER", "RIVN", "NIO"
    }

    if ticker in etfs:
        return f"AMEX:{ticker}"

    if ticker in nyse:
        return f"NYSE:{ticker}"

    return f"NASDAQ:{ticker}"


async def capture_chart(ticker, filename="chart.png"):
    symbol = tv_symbol(ticker)
    url = f"https://www.tradingview.com/chart/?symbol={symbol}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})

        await page.goto(url, timeout=60000)
        await page.wait_for_timeout(8000)

        await page.screenshot(path=filename, full_page=False)

        await browser.close()

    return filename
