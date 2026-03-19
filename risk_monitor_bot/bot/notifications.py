from __future__ import annotations

from aiogram import Bot

from db.models import RiskAssessment


async def send_risk_alert(bot: Bot, telegram_id: int, risk: RiskAssessment):
    emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk.risk_level, "🟢")
    summary = risk.summary
    article = summary.article if summary is not None else None

    summary_text = summary.summary_text if summary is not None else ""
    regions = ", ".join(summary.affected_regions) if summary and summary.affected_regions else "-"
    event_type = summary.event_type if summary is not None else "other"
    okved_codes = ", ".join(risk.okved_codes) if risk.okved_codes else "-"
    source_url = article.url if article and article.url else "https://t.me"

    text = (
        f"{emoji} <b>НОВЫЙ РИСК — {risk.risk_level.upper()}</b>\n\n"
        f"📰 {summary_text}\n\n"
        f"📋 ОКВЭД: {okved_codes}\n"
        f"📍 {regions}\n"
        f"🏷 Тип: {event_type}\n\n"
        f"🔗 <a href='{source_url}'>Источник</a>"
    )
    await bot.send_message(telegram_id, text, parse_mode="HTML")
