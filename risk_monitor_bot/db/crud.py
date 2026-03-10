from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Article, Notification, RiskAssessment, Summary, TelegramSource, User

RISK_PRIORITY = {"low": 1, "medium": 2, "high": 3}


def _normalize_str_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _risk_score(level: str) -> int:
    return RISK_PRIORITY.get((level or "").lower(), 2)


async def add_user(session: AsyncSession, telegram_id: int, username: str | None) -> User:
    existing = await get_user(session, telegram_id)
    if existing is not None:
        if username is not None and existing.username != username:
            existing.username = username
            await session.flush()
        return existing

    stmt = insert(User).values(telegram_id=telegram_id, username=username).returning(User)
    result = await session.execute(stmt)
    user = result.scalar_one()
    await session.flush()
    return user


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_user_settings(
    session: AsyncSession,
    telegram_id: int,
    okveds: list[str],
    regions: list[str],
    threshold: str,
) -> User:
    user = await get_user(session, telegram_id)
    if user is None:
        user = await add_user(session, telegram_id, username=None)

    stmt = (
        update(User)
        .where(User.id == user.id)
        .values(
            selected_okveds=_normalize_str_list(okveds),
            selected_regions=_normalize_str_list(regions),
            risk_threshold=threshold.lower(),
        )
        .returning(User)
    )
    result = await session.execute(stmt)
    updated = result.scalar_one()
    await session.flush()
    return updated


async def add_source(session: AsyncSession, channel_username: str) -> TelegramSource:
    normalized = channel_username.strip()

    stmt = select(TelegramSource).where(TelegramSource.channel_username == normalized)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    insert_stmt = insert(TelegramSource).values(channel_username=normalized).returning(TelegramSource)
    result = await session.execute(insert_stmt)
    source = result.scalar_one()
    await session.flush()
    return source


async def get_active_sources(session: AsyncSession) -> list[TelegramSource]:
    stmt = select(TelegramSource).where(TelegramSource.is_active.is_(True)).order_by(TelegramSource.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_source_last_message(session: AsyncSession, source_id: int, last_message_id: int) -> None:
    stmt = (
        update(TelegramSource)
        .where(TelegramSource.id == source_id)
        .values(last_parsed_message_id=func.greatest(TelegramSource.last_parsed_message_id, last_message_id))
    )
    await session.execute(stmt)
    await session.flush()


async def add_article(
    session: AsyncSession,
    source_id: int,
    message_id: int,
    text: str,
    url: str | None,
    published_at: datetime | None,
) -> Article | None:
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    duplicate_hash_stmt = select(Article.id).where(Article.hash == text_hash)
    if (await session.execute(duplicate_hash_stmt)).scalar_one_or_none() is not None:
        return None

    duplicate_message_stmt = select(Article.id).where(
        Article.source_id == source_id,
        Article.telegram_message_id == message_id,
    )
    if (await session.execute(duplicate_message_stmt)).scalar_one_or_none() is not None:
        return None

    stmt = (
        insert(Article)
        .values(
            source_id=source_id,
            telegram_message_id=message_id,
            text=text,
            url=url,
            published_at=published_at,
            hash=text_hash,
            is_processed=False,
        )
        .returning(Article)
    )
    result = await session.execute(stmt)
    article = result.scalar_one()
    await session.flush()
    return article


async def get_unprocessed_articles(session: AsyncSession, limit: int = 50) -> list[Article]:
    stmt = (
        select(Article)
        .where(Article.is_processed.is_(False))
        .order_by(Article.created_at.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_article_processed(session: AsyncSession, article_id: int) -> None:
    stmt = update(Article).where(Article.id == article_id).values(is_processed=True)
    await session.execute(stmt)
    await session.flush()


async def save_summary(
    session: AsyncSession,
    article_id: int,
    summary_text: str,
    industries: list[str],
    regions: list[str],
    event_type: str | None,
    tokens: int | None,
) -> Summary:
    existing_stmt = select(Summary).where(Summary.article_id == article_id)
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()

    values = {
        "summary_text": summary_text,
        "affected_industries": _normalize_str_list(industries),
        "affected_regions": _normalize_str_list(regions),
        "event_type": event_type,
        "tokens_used": tokens,
    }

    if existing is None:
        stmt = insert(Summary).values(article_id=article_id, **values).returning(Summary)
    else:
        stmt = update(Summary).where(Summary.id == existing.id).values(**values).returning(Summary)

    result = await session.execute(stmt)
    summary = result.scalar_one()
    await session.flush()
    return summary


async def save_risk_assessment(
    session: AsyncSession,
    summary_id: int,
    risk_level: str,
    confidence: float | None,
    okveds: list[str],
    explanation: str | None,
) -> RiskAssessment:
    existing_stmt = select(RiskAssessment).where(RiskAssessment.summary_id == summary_id)
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()

    values = {
        "risk_level": risk_level.lower(),
        "confidence": confidence,
        "okved_codes": _normalize_str_list(okveds),
        "explanation": explanation,
    }

    if existing is None:
        stmt = insert(RiskAssessment).values(summary_id=summary_id, **values).returning(RiskAssessment)
    else:
        stmt = (
            update(RiskAssessment)
            .where(RiskAssessment.id == existing.id)
            .values(**values)
            .returning(RiskAssessment)
        )

    result = await session.execute(stmt)
    risk = result.scalar_one()
    await session.flush()
    return risk


async def get_users_for_notification(
    session: AsyncSession,
    okved_codes: list[str],
    regions: list[str],
    min_risk_level: str,
) -> list[User]:
    normalized_okveds = _normalize_str_list(okved_codes)
    normalized_regions = _normalize_str_list(regions)
    current_risk_score = _risk_score(min_risk_level)
    dialect_name = session.bind.dialect.name if session.bind is not None else ""

    if dialect_name == "sqlite":
        users = list((await session.execute(select(User).where(User.is_active.is_(True)))).scalars().all())

        def _match_by_intersection(user_values: list[str], target_values: list[str]) -> bool:
            if not target_values:
                return True
            if not user_values:
                return True
            return bool(set(user_values).intersection(target_values))

        return [
            user
            for user in users
            if _match_by_intersection(user.selected_okveds, normalized_okveds)
            and _match_by_intersection(user.selected_regions, normalized_regions)
            and _risk_score(user.risk_threshold) <= current_risk_score
        ]

    stmt = select(User).where(User.is_active.is_(True))

    if normalized_okveds:
        stmt = stmt.where(
            or_(
                func.cardinality(User.selected_okveds) == 0,
                User.selected_okveds.overlap(normalized_okveds),
            )
        )

    if normalized_regions:
        stmt = stmt.where(
            or_(
                func.cardinality(User.selected_regions) == 0,
                User.selected_regions.overlap(normalized_regions),
            )
        )

    users = list((await session.execute(stmt)).scalars().all())

    return [user for user in users if _risk_score(user.risk_threshold) <= current_risk_score]


async def save_notification(session: AsyncSession, user_id: int, risk_assessment_id: int) -> Notification:
    stmt = (
        insert(Notification)
        .values(user_id=user_id, risk_assessment_id=risk_assessment_id, is_read=False)
        .returning(Notification)
    )
    result = await session.execute(stmt)
    notification = result.scalar_one()
    await session.flush()
    return notification


async def get_user_risks(session: AsyncSession, telegram_id: int, limit: int = 10) -> list[RiskAssessment]:
    stmt = (
        select(RiskAssessment)
        .join(Notification, Notification.risk_assessment_id == RiskAssessment.id)
        .join(User, User.id == Notification.user_id)
        .join(Summary, Summary.id == RiskAssessment.summary_id)
        .join(Article, Article.id == Summary.article_id)
        .options(selectinload(RiskAssessment.summary).selectinload(Summary.article))
        .where(User.telegram_id == telegram_id)
        .order_by(Notification.sent_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().unique().all())
