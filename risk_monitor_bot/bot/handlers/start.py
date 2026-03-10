from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import get_industries_keyboard
from bot.states.onboarding import OnboardingStates
from db import crud

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession):
    if message.from_user is None:
        return

    user = await crud.get_user(session, message.from_user.id)
    if user:
        await message.answer(
            "Вы уже зарегистрированы! /settings для изменения настроек, /risks для просмотра рисков."
        )
        return

    await crud.add_user(session, message.from_user.id, message.from_user.username)
    await state.update_data(selected_industries=[], selected_region="all", threshold="medium")
    await message.answer(
        "👋 Добро пожаловать в Risk Monitor!\n\n"
        "Я слежу за новостями и предупреждаю о рисках для вашего бизнеса.\n\n"
        "Давайте настроим — выберите вашу отрасль:",
        reply_markup=get_industries_keyboard(),
    )
    await state.set_state(OnboardingStates.choosing_industry)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start — регистрация и онбординг\n"
        "/settings — изменить фильтры\n"
        "/risks — посмотреть последние риски"
    )
