from __future__ import annotations

import asyncio
import logging

from tasks.celery_app import app

logger = logging.getLogger(__name__)


async def _process_batch() -> dict[str, int]:
    """Суммаризация + классификация необработанных статей."""
    from config import settings
    from db.crud import (
        get_unprocessed_articles,
        mark_article_processed,
        save_risk_assessment,
        save_summary,
    )
    from db.engine import session_maker
    from ml.risk_classifier import RiskClassifier
    from ml.summarizer import NewsSummarizer

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
        async with session_maker() as session:
            articles = await get_unprocessed_articles(session, limit=20)

            for article in articles:
                try:
                    summary_result = await summarizer.summarize(article.text)

                    if summary_result.summary_text in {"", "NOT_RELEVANT"}:
                        await mark_article_processed(session, article.id)
                        skipped_not_relevant += 1
                        continue

                    summary = await save_summary(
                        session,
                        article.id,
                        summary_result.summary_text,
                        summary_result.affected_industries,
                        summary_result.affected_regions,
                        summary_result.event_type,
                        summary_result.tokens_used,
                    )

                    risk_result = await classifier.classify(
                        summary_result.summary_text,
                        summary_result.affected_industries,
                        summary_result.event_type,
                    )

                    await save_risk_assessment(
                        session,
                        summary.id,
                        risk_result.risk_level,
                        risk_result.confidence,
                        risk_result.okved_codes,
                        risk_result.explanation,
                    )

                    await mark_article_processed(session, article.id)
                    processed += 1
                    logger.info("Processed article %s: risk=%s", article.id, risk_result.risk_level)
                except Exception as exc:
                    logger.error("Failed to process article %s: %s", article.id, exc)
                    continue

            await session.commit()
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
