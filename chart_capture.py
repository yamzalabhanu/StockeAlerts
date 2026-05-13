from playwright.async_api import async_playwright
from symbol_utils import tradingview_candidates, normalize_symbol, is_valid_symbol


TRADINGVIEW_INVALID_MARKERS = (
    "this symbol doesn't exist",
    "invalid symbol",
)


def _candidate_symbols(raw_symbol: str) -> list[str]:
    clean_symbol = normalize_symbol(raw_symbol)
    candidates = tradingview_candidates(clean_symbol)

    if ":" in str(raw_symbol):
        exchange = str(raw_symbol).split(":", 1)[0].strip().upper()
        explicit = f"{exchange}:{clean_symbol}"
        candidates = [explicit, *[candidate for candidate in candidates if candidate != explicit]]

    return candidates


async def _page_has_invalid_symbol_error(page) -> bool:
    body_text = (await page.locator("body").inner_text(timeout=3000)).lower()
    return any(marker in body_text for marker in TRADINGVIEW_INVALID_MARKERS)


async def capture_chart(ticker, filename="chart.png"):
    symbol_clean = normalize_symbol(ticker)

    if not is_valid_symbol(symbol_clean):
        raise ValueError(f"Invalid symbol for chart capture: {ticker}")

    candidates = _candidate_symbols(ticker)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})

        attempted = []
        for symbol in candidates:
            attempted.append(symbol)
            url = f"https://www.tradingview.com/chart/?symbol={symbol}"
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)
            if await _page_has_invalid_symbol_error(page):
                continue
            await page.wait_for_timeout(4000)
            await page.screenshot(path=filename, full_page=False)
            await browser.close()
            return filename

        await browser.close()

    raise ValueError(f"TradingView could not load a valid chart for {ticker}; tried {', '.join(attempted)}")

