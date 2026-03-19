import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from db.crud import add_source
from db.engine import create_tables, session_maker
from parser.telegram_parser import TelegramChannelParser


async def init_channels(channels: list[str]):
    await create_tables()

    parser = TelegramChannelParser(
        api_id=settings.TELEGRAM_API_ID,
        api_hash=settings.TELEGRAM_API_HASH,
        phone=settings.TELEGRAM_PHONE,
    )
    await parser.connect()

    try:
        async with session_maker() as session:
            for channel in channels:
                try:
                    info = await parser.get_channel_info(channel)
                    source = await add_source(session, channel)
                    source.channel_title = info["title"]
                    source.channel_id = info["id"]
                    await session.commit()
                    print(f"✅ Добавлен: {channel} ({info['title']})")
                except Exception as e:
                    await session.rollback()
                    print(f"❌ Ошибка с {channel}: {e}")
    finally:
        await parser.disconnect()


if __name__ == "__main__":
    channels = sys.argv[1:] if len(sys.argv) > 1 else settings.TELEGRAM_CHANNELS
    if not channels:
        print("Укажите каналы в .env (TELEGRAM_CHANNELS) или аргументами:")
        print("  python scripts/init_channels.py @channel1 @channel2")
        sys.exit(1)
    asyncio.run(init_channels(channels))
