from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from db import crud

router = Router(name="subscription")


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    await crud.set_user_subscription_status(
        session=session,
        telegram_id=message.from_user.id,
        is_subscribed=True,
    )
    await message.answer("Уведомления включены.")


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    await crud.set_user_subscription_status(
        session=session,
        telegram_id=message.from_user.id,
        is_subscribed=False,
    )
    await message.answer("Уведомления отключены.")
