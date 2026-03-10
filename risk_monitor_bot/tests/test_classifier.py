from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ml.risk_classifier import RiskClassifier


def _make_response(content: str, tokens: int = 50):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=tokens),
    )


@pytest.mark.asyncio
async def test_classify_high_risk(monkeypatch):
    response = _make_response(
        '{"risk_level":"high","confidence":0.9,"okved_codes":["49.41"],"explanation":"Высокий риск"}',
        tokens=77,
    )

    classifier = RiskClassifier(
        api_key="test",
        model="gpt-test",
        high_threshold=0.8,
        medium_threshold=0.5,
    )
    monkeypatch.setattr(classifier, "_classify_with_retry", AsyncMock(return_value=response))

    result = await classifier.classify("Сводка", ["Логистика"], "economic")

    assert result.risk_level == "high"
    assert result.confidence > 0.7
    assert result.okved_codes == ["49.41"]
    assert result.tokens_used == 77

    await classifier.close()


@pytest.mark.asyncio
async def test_classify_low_risk(monkeypatch):
    response = _make_response(
        '{"risk_level":"low","confidence":0.2,"okved_codes":[],"explanation":"Низкий риск"}',
    )

    classifier = RiskClassifier(
        api_key="test",
        model="gpt-test",
        high_threshold=0.8,
        medium_threshold=0.5,
    )
    monkeypatch.setattr(classifier, "_classify_with_retry", AsyncMock(return_value=response))

    result = await classifier.classify("Сводка", [], "other")

    assert result.risk_level == "low"
    assert result.confidence == 0.2

    await classifier.close()


@pytest.mark.asyncio
async def test_classify_invalid_risk_level_fallback_to_low(monkeypatch):
    response = _make_response(
        '{"risk_level":"critical","confidence":0.9,"okved_codes":["49"],"explanation":"Некорректный уровень"}',
    )

    classifier = RiskClassifier(
        api_key="test",
        model="gpt-test",
        high_threshold=0.8,
        medium_threshold=0.5,
    )
    monkeypatch.setattr(classifier, "_classify_with_retry", AsyncMock(return_value=response))

    result = await classifier.classify("Сводка", ["Транспорт"], "economic")

    assert result.risk_level == "low"

    await classifier.close()
