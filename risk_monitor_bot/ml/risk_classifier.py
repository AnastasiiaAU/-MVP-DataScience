from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

import httpx
from openai import APIError, AsyncOpenAI, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Ты — эксперт по оценке бизнес-рисков в России.
На основе краткого описания события оцени уровень риска для бизнеса.

Ответь СТРОГО в формате JSON:
{
  "risk_level": "high",
  "confidence": 0.85,
  "okved_codes": ["49.41", "49.42"],
  "explanation": "Вступившее в силу ограничение напрямую влияет на деятельность грузоперевозчиков в указанном регионе."
}

Критерии оценки:
- "high" (confidence > 0.7): Немедленное влияние. Вступивший в силу закон/запрет,
  авария нарушающая логистику, резкое изменение тарифов, судебное решение-прецедент.
- "medium" (confidence 0.4–0.7): Потенциальное влияние в горизонте 1-6 мес.
  Проект закона, обсуждение регулирования, тренд изменения цен.
- "low" (confidence < 0.4): Информационное событие без прямого влияния.
  Общие новости отрасли, статистика, аналитика.

Коды ОКВЭД — укажи конкретные коды, которые затрагивает событие.
Основные коды для справки:
- 01.xx — Сельское хозяйство
- 10.xx — Производство пищевых продуктов
- 49.xx — Транспорт сухопутный (49.41 — грузовой, 49.10 — ж/д)
- 52.xx — Складское хозяйство
- 68.xx — Недвижимость
- 41.xx — Строительство зданий
- 46.xx — Оптовая торговля
- 47.xx — Розничная торговля
Если точный код не определён, укажи ближайшую группу (например "49").
""".strip()

ALLOWED_LEVELS = {"low", "medium", "high"}


@dataclass(slots=True)
class RiskResult:
    risk_level: str
    confidence: float
    okved_codes: list[str]
    explanation: str
    tokens_used: int


class RiskClassifier:
    def __init__(
        self,
        api_key: str,
        model: str,
        high_threshold: float,
        medium_threshold: float,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self._owns_client = client is None
        self._http_client: httpx.AsyncClient | None = None

        if client is not None:
            self.client = client
        else:
            self._http_client = httpx.AsyncClient(timeout=60.0)
            # OpenRouter is OpenAI-compatible: chat.completions endpoint is the same.
            self.client = AsyncOpenAI(
                api_key=api_key,
                http_client=self._http_client,
                base_url="https://openrouter.ai/api/v1",
            )

    async def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()

    async def classify(
        self,
        summary_text: str,
        affected_industries: list[str],
        event_type: str,
    ) -> RiskResult:
        if not summary_text.strip():
            return RiskResult("low", 0.0, [], "", 0)

        payload = {
            "summary_text": summary_text.strip(),
            "affected_industries": affected_industries,
            "event_type": event_type,
        }

        try:
            response = await self._classify_with_retry(payload)
            tokens_used = int(getattr(response.usage, "total_tokens", 0) or 0)

            raw_content = response.choices[0].message.content or "{}"
            decoded = self._parse_json(raw_content)

            confidence = self._normalize_confidence(decoded.get("confidence"))
            risk_level = str(decoded.get("risk_level", "")).strip().lower()
            if risk_level not in ALLOWED_LEVELS:
                risk_level = "low"

            # Hard rule from requirements.
            if confidence < 0.3:
                risk_level = "low"

            okved_codes = self._to_str_list(decoded.get("okved_codes"))
            explanation = str(decoded.get("explanation", "")).strip()

            return RiskResult(
                risk_level=risk_level,
                confidence=confidence,
                okved_codes=okved_codes,
                explanation=explanation,
                tokens_used=tokens_used,
            )
        except APIError:
            logger.exception("OpenAI APIError while classifying risk")
        except JSONDecodeError:
            logger.exception("Failed to decode risk classifier JSON response")
        except Exception:
            logger.exception("Unexpected error while classifying risk")

        return RiskResult("low", 0.0, [], "", 0)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type(RateLimitError),
        reraise=True,
    )
    async def _classify_with_retry(self, payload: dict[str, Any]):
        return await self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            temperature=0.0,
        )

    def _risk_level_by_threshold(self, confidence: float) -> str:
        if confidence >= self.high_threshold:
            return "high"
        if confidence >= self.medium_threshold:
            return "medium"
        return "low"

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _parse_json(content: Any) -> dict[str, Any]:
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str):
            raise JSONDecodeError("Response content is not a JSON string", "", 0)
        return json.loads(content)

    @staticmethod
    def _to_str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item).strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result


_default_classifier: RiskClassifier | None = None


def _get_default_classifier() -> RiskClassifier:
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = RiskClassifier(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
            high_threshold=settings.HIGH_RISK_THRESHOLD,
            medium_threshold=settings.MEDIUM_RISK_THRESHOLD,
        )
    return _default_classifier


def calculate_risk_score(text: str) -> float:
    """
    Legacy heuristic helper for backward compatibility with old pipeline code.
    """
    normalized = text.lower()
    high_keywords = ("запрет", "авария", "санкции", "остановка", "банкротство")
    medium_keywords = ("проект", "обсуждение", "рост цен", "тариф", "проверка")
    score = 0.0
    score += 0.2 * sum(1 for keyword in high_keywords if keyword in normalized)
    score += 0.1 * sum(1 for keyword in medium_keywords if keyword in normalized)
    return max(0.0, min(1.0, round(score, 3)))


def risk_level_from_score(score: float) -> str:
    if score >= settings.HIGH_RISK_THRESHOLD:
        return "high"
    if score >= settings.MEDIUM_RISK_THRESHOLD:
        return "medium"
    return "low"


def classify_risk(text: str) -> tuple[float, str]:
    """
    Legacy sync API used by existing tasks; returns (score, level).
    """
    score = calculate_risk_score(text)
    return score, risk_level_from_score(score)
