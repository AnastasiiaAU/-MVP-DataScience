from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db import crud
from db.engine import get_session_maker
from db.models import TelegramSource
from parser.telegram_parser import TelegramChannelParser, build_parser_from_settings

logger = logging.getLogger(__name__)


class ParsingManager:
    def __init__(
        self,
        parser: TelegramChannelParser,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        self.parser = parser
        self.session_maker = session_maker

    async def run_parsing_cycle(self) -> int:
        total_new_articles = 0

        async with self.session_maker() as session:
            sources = await crud.get_active_sources(session)

        if not sources:
            logger.info("No active sources for parsing")
            return 0

        for index, source in enumerate(sources):
            saved_for_source = 0
            try:
                messages = await self.parser.fetch_new_messages(
                    source_id=source.id,
                    channel=source.channel_username,
                    last_message_id=source.last_parsed_message_id,
                )

                if messages:
                    max_message_id = max(msg.message_id for msg in messages)

                    async with self.session_maker() as session:
                        for message in messages:
                            article = await crud.add_article(
                                session=session,
                                source_id=message.source_id,
                                message_id=message.message_id,
                                text=message.text,
                                url=message.url,
                                published_at=message.published_at,
                            )
                            if article is not None:
                                saved_for_source += 1

                        await crud.update_source_last_message(
                            session=session,
                            source_id=source.id,
                            last_message_id=max_message_id,
                        )
                        await session.commit()

                logger.info("Parsed %s: %s new messages", source.channel_username, saved_for_source)
                total_new_articles += saved_for_source
            except Exception:
                logger.exception("Failed parsing source %s", source.channel_username)

            if index < len(sources) - 1:
                await asyncio.sleep(2)

        return total_new_articles

    async def add_channel(self, channel_username: str) -> TelegramSource:
        await self.parser.connect()
        try:
            info = await self.parser.get_channel_info(channel_username)

            async with self.session_maker() as session:
                source = await crud.add_source(session=session, channel_username=channel_username)
                source.channel_title = info.get("title")
                source.channel_id = info.get("id")
                await session.flush()
                await session.commit()

            return source
        finally:
            await self.parser.disconnect()


class ParserManager(ParsingManager):
    def __init__(self) -> None:
        super().__init__(
            parser=build_parser_from_settings(),
            session_maker=get_session_maker(),
        )
