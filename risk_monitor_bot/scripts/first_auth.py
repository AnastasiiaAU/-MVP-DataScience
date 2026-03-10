import asyncio

from telethon import TelegramClient

from config import settings


async def first_auth():
    """Первичная авторизация Telethon — запросит номер и код."""
    client = TelegramClient(
        "sessions/parser_session",
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )
    await client.start(phone=settings.TELEGRAM_PHONE)
    me = await client.get_me()
    print(f"Авторизация успешна: {me.first_name} (@{me.username})")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(first_auth())
