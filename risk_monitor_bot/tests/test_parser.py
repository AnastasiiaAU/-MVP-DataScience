from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parser.telegram_parser import TelegramChannelParser


class AsyncMessageIterator:
    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
async def test_fetch_new_messages_formats_raw_messages():
    now = datetime.now(timezone.utc)
    messages = [
        SimpleNamespace(id=3, text="x" * 80, raw_text=None, date=now),
        SimpleNamespace(id=1, text="y" * 90, raw_text=None, date=now),
        SimpleNamespace(id=2, text="z" * 70, raw_text=None, date=now),
    ]

    fake_client = MagicMock()
    fake_client.is_connected.return_value = True
    fake_client.iter_messages.return_value = AsyncMessageIterator(messages)

    with patch("parser.telegram_parser.TelegramClient", return_value=fake_client):
        parser = TelegramChannelParser(api_id=1, api_hash="hash", phone="+70000000000")

    result = await parser.fetch_new_messages(source_id=5, channel="@demo_channel", last_message_id=0)

    assert len(result) == 3
    assert [item.message_id for item in result] == [1, 2, 3]
    assert result[0].source_id == 5
    assert result[0].url == "https://t.me/demo_channel/1"


@pytest.mark.asyncio
async def test_fetch_new_messages_skips_empty_text_messages():
    now = datetime.now(timezone.utc)
    messages = [
        SimpleNamespace(id=1, text=None, raw_text=None, date=now),
        SimpleNamespace(id=2, text="q" * 70, raw_text=None, date=now),
    ]

    fake_client = MagicMock()
    fake_client.is_connected.return_value = True
    fake_client.iter_messages.return_value = AsyncMessageIterator(messages)

    with patch("parser.telegram_parser.TelegramClient", return_value=fake_client):
        parser = TelegramChannelParser(api_id=1, api_hash="hash", phone="+70000000000")

    result = await parser.fetch_new_messages(source_id=1, channel="@demo", last_message_id=0)

    assert len(result) == 1
    assert result[0].message_id == 2


@pytest.mark.asyncio
async def test_fetch_new_messages_skips_short_messages():
    now = datetime.now(timezone.utc)
    messages = [
        SimpleNamespace(id=1, text="too short", raw_text=None, date=now),
        SimpleNamespace(id=2, text="a" * 50, raw_text=None, date=now),
    ]

    fake_client = MagicMock()
    fake_client.is_connected.return_value = True
    fake_client.iter_messages.return_value = AsyncMessageIterator(messages)

    with patch("parser.telegram_parser.TelegramClient", return_value=fake_client):
        parser = TelegramChannelParser(api_id=1, api_hash="hash", phone="+70000000000")

    result = await parser.fetch_new_messages(source_id=1, channel="@demo", last_message_id=0)

    assert len(result) == 1
    assert result[0].message_id == 2


@pytest.mark.asyncio
async def test_fetch_new_messages_handles_flood_wait(monkeypatch):
    import parser.telegram_parser as parser_module

    class DummyFloodWaitError(Exception):
        def __init__(self, seconds: int):
            super().__init__(f"wait {seconds}")
            self.seconds = seconds

    now = datetime.now(timezone.utc)
    state = {"calls": 0}

    def iter_messages_side_effect(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            raise DummyFloodWaitError(2)
        return AsyncMessageIterator([SimpleNamespace(id=10, text="x" * 80, raw_text=None, date=now)])

    fake_client = MagicMock()
    fake_client.is_connected.return_value = True
    fake_client.iter_messages = MagicMock(side_effect=iter_messages_side_effect)

    sleep_mock = AsyncMock()
    monkeypatch.setattr(parser_module, "FloodWaitError", DummyFloodWaitError)
    monkeypatch.setattr(parser_module.asyncio, "sleep", sleep_mock)

    with patch("parser.telegram_parser.TelegramClient", return_value=fake_client):
        parser = TelegramChannelParser(api_id=1, api_hash="hash", phone="+70000000000")

    result = await parser.fetch_new_messages(source_id=1, channel="@demo", last_message_id=0)

    sleep_mock.assert_awaited_once_with(2)
    assert len(result) == 1
    assert result[0].message_id == 10
