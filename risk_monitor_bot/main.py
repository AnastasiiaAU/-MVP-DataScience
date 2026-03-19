import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from bot.handlers import risks, settings as settings_handlers, start
from bot.middlewares.db_session import DbSessionMiddleware
from config import settings
from db.engine import create_tables, session_maker


async def main():
    logging.basicConfig(level=logging.INFO)

    await create_tables()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()

    dp.update.middleware(DbSessionMiddleware(session_pool=session_maker))

    dp.include_router(start.router)
    dp.include_router(settings_handlers.router)
    dp.include_router(risks.router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
