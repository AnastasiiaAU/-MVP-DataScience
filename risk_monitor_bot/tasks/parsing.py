from __future__ import annotations

import asyncio
import logging

from tasks.celery_app import app

logger = logging.getLogger(__name__)


async def _parse_channels() -> int:
    """Асинхронная функция парсинга всех каналов."""
    from config import settings
    from db.engine import session_maker
    from parser.manager import ParsingManager
    from parser.telegram_parser import TelegramChannelParser

    parser = TelegramChannelParser(
        api_id=settings.TELEGRAM_API_ID,
        api_hash=settings.TELEGRAM_API_HASH,
        phone=settings.TELEGRAM_PHONE,
    )

    try:
        await parser.connect()
        manager = ParsingManager(parser=parser, session_maker=session_maker)
        count = await manager.run_parsing_cycle()
        logger.info("Parsing cycle complete: %s new articles", count)
        return count
    finally:
        await parser.disconnect()


@app.task(name="tasks.parsing.parse_all_channels", bind=True, max_retries=3)
def parse_all_channels(self):
    """Celery-таск: запуск парсинга всех Telegram-каналов."""
    try:
        return asyncio.run(_parse_channels())
    except Exception as exc:
        logger.error("Parsing failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)
