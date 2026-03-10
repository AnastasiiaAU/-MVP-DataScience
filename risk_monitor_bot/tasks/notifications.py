from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from tasks.celery_app import app

logger = logging.getLogger(__name__)


async def _send_notifications() -> dict[str, int]:
    """Найти новые RiskAssessment без уведомлений и разослать подходящим пользователям."""
    from bot.notifications import send_risk_alert
    from config import settings
    from db.crud import get_users_for_notification, save_notification
    from db.engine import session_maker
    from db.models import Notification, RiskAssessment, Summary

    sent_total = 0
    assessments_total = 0

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        async with session_maker() as session:
            pending_stmt = (
                select(RiskAssessment)
                .join(Summary, Summary.id == RiskAssessment.summary_id)
                .outerjoin(Notification, Notification.risk_assessment_id == RiskAssessment.id)
                .where(Notification.id.is_(None))
                .options(selectinload(RiskAssessment.summary).selectinload(Summary.article))
                .order_by(RiskAssessment.created_at.asc())
            )
            pending_risks = list((await session.execute(pending_stmt)).scalars().all())

            for risk in pending_risks:
                assessments_total += 1
                summary = risk.summary
                regions = summary.affected_regions if summary is not None else []

                users = await get_users_for_notification(
                    session=session,
                    okved_codes=risk.okved_codes,
                    regions=regions,
                    min_risk_level=risk.risk_level,
                )

                for user in users:
                    try:
                        await send_risk_alert(bot=bot, telegram_id=user.telegram_id, risk=risk)
                        await save_notification(
                            session=session,
                            user_id=user.id,
                            risk_assessment_id=risk.id,
                        )
                        sent_total += 1
                        await asyncio.sleep(0.05)
                    except Exception as exc:
                        logger.error(
                            "Failed to send notification to user_id=%s for risk_id=%s: %s",
                            user.id,
                            risk.id,
                            exc,
                        )

            await session.commit()
    finally:
        await bot.session.close()

    logger.info("Notifications cycle complete: assessments=%s sent=%s", assessments_total, sent_total)
    return {"assessments": assessments_total, "sent": sent_total}


@app.task(name="tasks.notifications.send_pending_notifications")
def send_pending_notifications():
    return asyncio.run(_send_notifications())
