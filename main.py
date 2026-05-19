import asyncio

from bot import StockTechnicalAIBot
from config import BASE_WATCHLIST
from bot_enhancements import apply_enhancements
from logging_setup import enable_timestamped_prints


async def main():
    """Launch the advanced technical AI bot with adaptive + regime enhancements."""

    # 🔥 Inject adaptive learning + market regime scoring
    apply_enhancements(StockTechnicalAIBot)

    bot = StockTechnicalAIBot(BASE_WATCHLIST)
    await bot.run()


if __name__ == "__main__":
    enable_timestamped_prints()
    asyncio.run(main())
