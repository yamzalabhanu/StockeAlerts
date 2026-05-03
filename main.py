import asyncio

from bot import StockTechnicalAIBot
from config import BASE_WATCHLIST


async def main():
    """Launch the advanced technical AI bot.

    This replaces the older standalone scanner and ensures running:

        python main.py

    uses the advanced features implemented in:
    - bot.py
    - bot_technical.py
    - chart_capture.py
    - intraday_confirm.py
    """
    bot = StockTechnicalAIBot(BASE_WATCHLIST)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
