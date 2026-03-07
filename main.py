import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties


from config import TELEGRAM_BOT_TOKEN
from db.mongo import connect, disconnect
from bot.handlers import start, message, commands, callbacks
from bot.middlewares.debounce import DebounceMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from services.scheduler import init_scheduler, shutdown_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Starting Fix My Love bot...")

    await connect()
    logger.info("MongoDB connected")

    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(),
    )

    dp = Dispatcher()

    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(DebounceMiddleware())

    dp.include_router(start.router)
    dp.include_router(commands.router)
    dp.include_router(message.router)
    dp.include_router(callbacks.router)

    init_scheduler(bot)
    logger.info("Scheduler initialized")

    try:
        logger.info("Bot started polling")
        await dp.start_polling(bot)
    finally:
        shutdown_scheduler()
        await disconnect()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
