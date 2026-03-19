from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.keyboards.inline import get_risk_detail_keyboard
from db import crud
from db.models import Article, Notification, RiskAssessment, Summary, User

router = Router(name="risks")


@router.message(Command("risks"))
async def cmd_risks(message: Message, session: AsyncSession):
    if message.from_user is None:
        return

    risks = await crud.get_user_risks(session, message.from_user.id, limit=10)

    if not risks:
        await message.answer("📭 Пока нет рисков по вашим подпискам.")
        return

    emoji_map = {"high": "🔴", "medium": "🟡", "low": "🟢"}

    for risk in risks:
        summary = risk.summary
        article = summary.article if summary is not None else None
        published_at = article.published_at if article is not None else None
        published_text = published_at.strftime("%d.%m.%Y %H:%M") if published_at else "Не указана"

        emoji = emoji_map.get(risk.risk_level, "🟢")
        confidence = risk.confidence or 0.0
        summary_text = summary.summary_text if summary is not None else "Сводка недоступна"
        regions = summary.affected_regions if summary is not None else []

        text = (
            f"{emoji} <b>{risk.risk_level.upper()}</b> | "
            f"Уверенность: {confidence:.0%}\n\n"
            f"📰 {summary_text}\n\n"
            f"📋 ОКВЭД: {', '.join(risk.okved_codes) if risk.okved_codes else 'Не определён'}\n"
            f"📍 Регионы: {', '.join(regions) if regions else 'Не указан'}\n"
            f"📅 {published_text}"
        )

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_risk_detail_keyboard(
                risk.id,
                source_url=article.url if article is not None else None,
            ),
        )


@router.callback_query(F.data.startswith("risk_detail:"))
async def callback_risk_detail(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.data is None or callback.message is None:
        return

    risk_id_raw = callback.data.split(":", maxsplit=1)[1]
    if not risk_id_raw.isdigit():
        await callback.answer("Некорректный ID риска", show_alert=True)
        return

    risk_id = int(risk_id_raw)

    stmt = (
        select(RiskAssessment)
        .join(Notification, Notification.risk_assessment_id == RiskAssessment.id)
        .join(User, User.id == Notification.user_id)
        .join(Summary, Summary.id == RiskAssessment.summary_id)
        .join(Article, Article.id == Summary.article_id)
        .options(selectinload(RiskAssessment.summary).selectinload(Summary.article))
        .where(RiskAssessment.id == risk_id, User.telegram_id == callback.from_user.id)
        .limit(1)
    )
    risk = (await session.execute(stmt)).scalar_one_or_none()

    if risk is None:
        await callback.answer("Риск не найден", show_alert=True)
        return

    summary = risk.summary
    article = summary.article if summary is not None else None
    source_url = article.url if article and article.url else "Источник недоступен"
    industries = summary.affected_industries if summary is not None else []
    regions = summary.affected_regions if summary is not None else []

    details_text = (
        "<b>Детали риска</b>\n"
        f"Уровень: <b>{risk.risk_level.upper()}</b>\n"
        f"Уверенность: {(risk.confidence or 0.0):.0%}\n"
        f"Тип события: {summary.event_type if summary else 'other'}\n"
        f"ОКВЭД: {', '.join(risk.okved_codes) if risk.okved_codes else '-'}\n"
        f"Отрасли: {', '.join(industries) if industries else '-'}\n"
        f"Регионы: {', '.join(regions) if regions else '-'}\n\n"
        f"Обоснование: {risk.explanation or 'Нет пояснения'}\n\n"
        f"Источник: {source_url}"
    )

    await callback.message.answer(details_text)
    await callback.answer()
