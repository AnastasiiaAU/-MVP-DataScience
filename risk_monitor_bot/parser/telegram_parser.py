from __future__ import annotations

import asyncio
import logging
import os
from getpass import getpass
from typing import Any
from urllib.parse import urlparse

from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.functions.channels import GetFullChannelRequest

from config import settings
from parser.base import BaseParser, RawMessage

logger = logging.getLogger(__name__)


class TelegramChannelParser(BaseParser):
    def __init__(self, api_id: int, api_hash: str, phone: str) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        os.makedirs("sessions", exist_ok=True)
        self.client = TelegramClient("sessions/parser_session", self.api_id, self.api_hash)

    async def connect(self) -> None:
        if self.client.is_connected():
            return

        await self.client.connect()
        if await self.client.is_user_authorized():
            return

        logger.info("Telethon session is not authorized. Starting sign-in flow for %s", self.phone)
        await self.client.send_code_request(self.phone)
        code = input("Enter Telegram login code: ").strip()

        try:
            await self.client.sign_in(phone=self.phone, code=code)
        except SessionPasswordNeededError:
            password = getpass("Enter Telegram 2FA password: ")
            await self.client.sign_in(password=password)

        logger.info("Telethon authorization completed successfully")

    async def disconnect(self) -> None:
        if self.client.is_connected():
            await self.client.disconnect()

    async def fetch_new_messages(
        self,
        source_id: int,
        channel: str,
        last_message_id: int,
    ) -> list[RawMessage]:
        if not self.client.is_connected():
            await self.connect()

        channel_ref = self._to_channel_ref(channel)
        channel_slug = self._to_channel_slug(channel)
        parsed: list[RawMessage] = []

        while True:
            try:
                async for message in self.client.iter_messages(
                    entity=channel_ref,
                    min_id=last_message_id,
                    limit=settings.PARSE_MESSAGE_LIMIT,
                ):
                    text = (message.text or message.raw_text or "").strip()
                    if not text or len(text) < 50:
                        continue

                    parsed.append(
                        RawMessage(
                            source_id=source_id,
                            message_id=message.id,
                            text=text,
                            url=f"https://t.me/{channel_slug}/{message.id}",
                            published_at=message.date,
                        )
                    )
                break
            except FloodWaitError as error:
                logger.warning(
                    "FloodWait while fetching %s (source_id=%s). Sleep %s seconds",
                    channel,
                    source_id,
                    error.seconds,
                )
                await asyncio.sleep(error.seconds)
            except Exception:
                logger.exception("Failed to fetch messages for channel=%s", channel)
                return []

        parsed.sort(key=lambda item: item.message_id)
        logger.info(
            "Fetched %s messages from %s (source_id=%s, min_id=%s)",
            len(parsed),
            channel,
            source_id,
            last_message_id,
        )
        return parsed

    async def get_channel_info(self, channel_username: str) -> dict[str, Any]:
        if not self.client.is_connected():
            await self.connect()

        channel_ref = self._to_channel_ref(channel_username)
        entity = await self.client.get_entity(channel_ref)

        participants_count: int | None = None
        try:
            full_info = await self.client(GetFullChannelRequest(entity))
            participants_count = getattr(full_info.full_chat, "participants_count", None)
        except Exception:
            logger.debug("Could not fetch participants count for %s", channel_username)

        return {
            "title": getattr(entity, "title", None),
            "id": getattr(entity, "id", None),
            "participants_count": participants_count,
        }

    @staticmethod
    def _to_channel_ref(channel: str) -> str:
        cleaned = channel.strip()
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            parsed = urlparse(cleaned)
            cleaned = parsed.path.strip("/")

        if "/" in cleaned:
            cleaned = cleaned.split("/", maxsplit=1)[0]

        if not cleaned:
            return channel

        if cleaned.startswith("@") or cleaned.startswith("+"):
            return cleaned

        return f"@{cleaned}"

    @staticmethod
    def _to_channel_slug(channel: str) -> str:
        cleaned = channel.strip()
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            parsed = urlparse(cleaned)
            cleaned = parsed.path.strip("/")

        if "/" in cleaned:
            cleaned = cleaned.split("/", maxsplit=1)[0]

        return cleaned.lstrip("@")


def build_parser_from_settings() -> TelegramChannelParser:
    return TelegramChannelParser(
        api_id=settings.TELEGRAM_API_ID,
        api_hash=settings.TELEGRAM_API_HASH,
        phone=settings.TELEGRAM_PHONE,
    )
