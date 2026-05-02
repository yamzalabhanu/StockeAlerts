from bot import StockTechnicalAIBot
from config import BASE_WATCHLIST
import asyncio


if __name__ == "__main__":
    bot = StockTechnicalAIBot(BASE_WATCHLIST)
    asyncio.run(bot.run())
