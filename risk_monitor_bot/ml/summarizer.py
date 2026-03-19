from __future__ import annotations

import asyncio
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
Ты — аналитик бизнес-рисков. Твоя задача — проанализировать новостное сообщение
и извлечь структурированную информацию.

Ответь СТРОГО в формате JSON:
{
  "summary": "Краткое содержание в 3-5 предложениях. Только факты, без воды.",
  "affected_industries": ["Грузоперевозки", "Логистика"],
  "affected_regions": ["Московская область"],
  "event_type": "legislation"
}

Типы событий:
- "legislation" — новый закон, постановление, приказ, регулирование
- "accident" — авария, ЧП, техногенное событие
- "economic" — экономический фактор (курс, цены, санкции, тарифы)
- "court" — судебное решение, прецедент
- "other" — не подходит ни одна категория

Если новость не относится к бизнес-рискам (мемы, реклама, off-topic),
верни: {"summary": "NOT_RELEVANT", "affected_industries": [], "affected_regions": [], "event_type": "other"}
""".strip()

ALLOWED_EVENT_TYPES = {"legislation", "accident", "economic", "court", "other"}


@dataclass(slots=True)
class SummaryResult:
    summary_text: str
    affected_industries: list[str]
    affected_regions: list[str]
    event_type: str
    tokens_used: int


class NewsSummarizer:
    MAX_INPUT_TOKENS = 3000

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        # AsyncOpenAI uses httpx transport; explicit client keeps behavior predictable.
        self._http_client = httpx.AsyncClient(timeout=60.0)
        # OpenRouter is OpenAI-compatible: chat.completions endpoint is the same.
        self.client = AsyncOpenAI(
            api_key=api_key,
            http_client=self._http_client,
            base_url="https://openrouter.ai/api/v1",
        )

    async def close(self) -> None:
        await self._http_client.aclose()

    async def summarize(self, text: str) -> SummaryResult:
        prepared_text = self._prepare_text(text)

        if not prepared_text.strip():
            return SummaryResult("", [], [], "other", 0)

        try:
            response = await self._chat_completion_with_retry(prepared_text)
            tokens_used = int(getattr(response.usage, "total_tokens", 0) or 0)

            raw_content = response.choices[0].message.content or "{}"
            payload = self._parse_response_json(raw_content)

            summary = str(payload.get("summary", "")).strip()
            if summary == "NOT_RELEVANT":
                return SummaryResult("", [], [], "other", tokens_used)

            industries = self._to_str_list(payload.get("affected_industries"))
            regions = self._to_str_list(payload.get("affected_regions"))
            event_type = str(payload.get("event_type", "other")).strip().lower()
            if event_type not in ALLOWED_EVENT_TYPES:
                event_type = "other"

            return SummaryResult(
                summary_text=summary,
                affected_industries=industries,
                affected_regions=regions,
                event_type=event_type,
                tokens_used=tokens_used,
            )
        except APIError:
            logger.exception("OpenAI APIError while summarizing text")
        except JSONDecodeError:
            logger.exception("Failed to decode LLM JSON response")
        except Exception:
            logger.exception("Unexpected error while summarizing text")

        return SummaryResult("", [], [], "other", 0)

    async def summarize_batch(self, texts: list[str]) -> list[SummaryResult]:
        total = len(texts)
        semaphore = asyncio.Semaphore(5)
        progress_lock = asyncio.Lock()
        progress = 0

        async def _worker(text: str) -> SummaryResult:
            nonlocal progress
            async with semaphore:
                result = await self.summarize(text)
                async with progress_lock:
                    progress += 1
                    logger.info("Summarized %s/%s", progress, total)
                return result

        return await asyncio.gather(*(_worker(text) for text in texts))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type(RateLimitError),
        reraise=True,
    )
    async def _chat_completion_with_retry(self, text: str):
        return await self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
        )

    def _prepare_text(self, text: str) -> str:
        normalized = (text or "").strip()
        if len(normalized) <= self.MAX_INPUT_TOKENS:
            return normalized
        return f"{normalized[: self.MAX_INPUT_TOKENS]}\n\n[текст сокращён]"

    @staticmethod
    def _parse_response_json(content: Any) -> dict[str, Any]:
        if isinstance(content, list):
            # Defensive fallback for SDK variants that may return structured blocks.
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
            cleaned = str(item).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
        return result


_default_summarizer: NewsSummarizer | None = None


def _get_default_summarizer() -> NewsSummarizer:
    global _default_summarizer
    if _default_summarizer is None:
        _default_summarizer = NewsSummarizer(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
        )
    return _default_summarizer


async def summarize_text(text: str) -> str:
    result = await _get_default_summarizer().summarize(text)
    return result.summary_text
