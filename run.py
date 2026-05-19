import asyncio

from bot import StockTechnicalAIBot
from bot_enhancements import apply_enhancements
from config import BASE_WATCHLIST
from logging_setup import enable_timestamped_prints


if __name__ == "__main__":
    enable_timestamped_prints()
    apply_enhancements(StockTechnicalAIBot)
    bot = StockTechnicalAIBot(BASE_WATCHLIST)
    asyncio.run(bot.run())
