from __future__ import annotations

import asyncio
import logging

from tasks.celery_app import app

logger = logging.getLogger(__name__)


async def _process_batch() -> dict[str, int]:
    """Суммаризация + классификация необработанных статей.
    Каждая статья обрабатывается в отдельной сессии, чтобы не держать соединение с БД
    открытым во время долгих HTTP-вызовов к OpenAI (избегаем asyncpg "another operation in progress").
    """
    from config import settings
    from db.crud import (
        get_unprocessed_articles,
        mark_article_processed,
        save_risk_assessment,
        save_summary,
    )
    from db.engine import engine, session_maker
    from ml.risk_classifier import RiskClassifier
    from ml.summarizer import NewsSummarizer

    # Каждый asyncio.run() создаёт новый event loop; старые соединения привязаны к прошлому loop.
    # Сбрасываем пул, чтобы новые соединения создавались в текущем loop.
    engine.dispose()

    summarizer = NewsSummarizer(api_key=settings.OPENAI_API_KEY, model=settings.OPENAI_MODEL)
    classifier = RiskClassifier(
        api_key=settings.OPENAI_API_KEY,
        model=settings.OPENAI_MODEL,
        high_threshold=settings.HIGH_RISK_THRESHOLD,
        medium_threshold=settings.MEDIUM_RISK_THRESHOLD,
    )

    processed = 0
    skipped_not_relevant = 0

    try:
        # Получить список статей и сразу закрыть сессию — соединение не держим во время API-вызовов
        # Небольшой батч и паузы между статьями, чтобы не упираться в лимит OpenAI (429)
        async with session_maker() as session:
            articles = await get_unprocessed_articles(session, limit=5)
            # Снять объекты с сессии и сохранить нужные поля в память
            work = [(a.id, a.text) for a in articles]

        for i, (article_id, text) in enumerate(work):
            if i > 0:
                await asyncio.sleep(2)  # пауза между статьями, чтобы не получать 429 от OpenAI
            try:
                summary_result = await summarizer.summarize(text)

                if summary_result.summary_text in {"", "NOT_RELEVANT"}:
                    async with session_maker() as session:
                        await mark_article_processed(session, article_id)
                        await session.commit()
                    skipped_not_relevant += 1
                    continue

                risk_result = await classifier.classify(
                    summary_result.summary_text,
                    summary_result.affected_industries,
                    summary_result.event_type,
                )

                # Одна короткая сессия на запись: summary + risk_assessment + mark_processed
                async with session_maker() as session:
                    summary = await save_summary(
                        session,
                        article_id,
                        summary_result.summary_text,
                        summary_result.affected_industries,
                        summary_result.affected_regions,
                        summary_result.event_type,
                        summary_result.tokens_used,
                    )
                    await save_risk_assessment(
                        session,
                        summary.id,
                        risk_result.risk_level,
                        risk_result.confidence,
                        risk_result.okved_codes,
                        risk_result.explanation,
                    )
                    await mark_article_processed(session, article_id)
                    await session.commit()
                processed += 1
                logger.info("Processed article %s: risk=%s", article_id, risk_result.risk_level)
            except Exception as exc:
                logger.error("Failed to process article %s: %s", article_id, exc)
                continue
    finally:
        await summarizer.close()
        await classifier.close()

    return {
        "processed": processed,
        "not_relevant": skipped_not_relevant,
    }


@app.task(name="tasks.processing.process_articles_batch")
def process_articles_batch():
    return asyncio.run(_process_batch())
