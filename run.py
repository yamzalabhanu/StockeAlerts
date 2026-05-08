import asyncio

from bot import StockTechnicalAIBot
from bot_enhancements import apply_enhancements
from config import BASE_WATCHLIST


if __name__ == "__main__":
    apply_enhancements(StockTechnicalAIBot)
    bot = StockTechnicalAIBot(BASE_WATCHLIST)
    asyncio.run(bot.run())
