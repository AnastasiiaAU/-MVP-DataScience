from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ml.summarizer import NewsSummarizer


def _make_response(content: str, tokens: int = 123):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=tokens),
    )


@pytest.mark.asyncio
async def test_summarize_normal_response(monkeypatch):
    response = _make_response(
        '{"summary":"Краткая сводка.","affected_industries":["Логистика"],"affected_regions":["ЦФО"],"event_type":"economic"}',
        tokens=111,
    )

    summarizer = NewsSummarizer(api_key="test", model="gpt-test")
    monkeypatch.setattr(summarizer, "_chat_completion_with_retry", AsyncMock(return_value=response))

    result = await summarizer.summarize("Текст новости" * 10)

    assert result.summary_text == "Краткая сводка."
    assert result.affected_industries == ["Логистика"]
    assert result.affected_regions == ["ЦФО"]
    assert result.event_type == "economic"
    assert result.tokens_used == 111

    await summarizer.close()


@pytest.mark.asyncio
async def test_summarize_not_relevant(monkeypatch):
    response = _make_response(
        '{"summary":"NOT_RELEVANT","affected_industries":[],"affected_regions":[],"event_type":"other"}',
        tokens=42,
    )

    summarizer = NewsSummarizer(api_key="test", model="gpt-test")
    monkeypatch.setattr(summarizer, "_chat_completion_with_retry", AsyncMock(return_value=response))

    result = await summarizer.summarize("Мем или реклама")

    assert result.summary_text == ""
    assert result.affected_industries == []
    assert result.affected_regions == []
    assert result.event_type == "other"
    assert result.tokens_used == 42

    await summarizer.close()


@pytest.mark.asyncio
async def test_summarize_invalid_json_returns_empty_result(monkeypatch):
    response = _make_response("{invalid json", tokens=10)

    summarizer = NewsSummarizer(api_key="test", model="gpt-test")
    monkeypatch.setattr(summarizer, "_chat_completion_with_retry", AsyncMock(return_value=response))

    result = await summarizer.summarize("Любой текст")

    assert result.summary_text == ""
    assert result.affected_industries == []
    assert result.affected_regions == []
    assert result.event_type == "other"

    await summarizer.close()


@pytest.mark.asyncio
async def test_summarize_truncates_long_text(monkeypatch):
    response = _make_response(
        '{"summary":"ok","affected_industries":[],"affected_regions":[],"event_type":"other"}',
        tokens=15,
    )

    summarizer = NewsSummarizer(api_key="test", model="gpt-test")
    chat_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(summarizer, "_chat_completion_with_retry", chat_mock)

    long_text = "x" * 5000
    await summarizer.summarize(long_text)

    sent_text = chat_mock.await_args.args[0]
    assert "[текст сокращён]" in sent_text
    assert sent_text.startswith("x" * summarizer.MAX_INPUT_TOKENS)

    await summarizer.close()
