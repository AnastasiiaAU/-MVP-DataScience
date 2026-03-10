from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import (
    INDUSTRIES,
    REGIONS,
    THRESHOLDS,
    get_industries_keyboard,
    get_regions_keyboard,
    get_threshold_keyboard,
)
from bot.states.onboarding import OnboardingStates
from db import crud

router = Router(name="settings")

INDUSTRY_TO_OKVED: dict[str, list[str]] = {
    "transport": ["49", "52"],
    "agriculture": ["01"],
    "construction": ["41"],
    "trade": ["46", "47"],
    "manufacturing": ["10"],
}

INDUSTRY_LABEL = dict(INDUSTRIES)
REGION_LABEL = dict(REGIONS)
THRESHOLD_LABEL = dict(THRESHOLDS)
REGION_KEY_BY_LABEL = {value: key for key, value in REGIONS}


def _extract_industries_from_okveds(okveds: list[str]) -> list[str]:
    selected: list[str] = []
    okved_set = set(okveds)
    for industry, codes in INDUSTRY_TO_OKVED.items():
        if any(code in okved_set for code in codes):
            selected.append(industry)
    return selected


def _build_settings_summary(industry_keys: list[str], region_key: str, threshold: str) -> str:
    industry_titles = [INDUSTRY_LABEL.get(key, key) for key in industry_keys]
    industries_text = ", ".join(industry_titles) if industry_titles else "Не выбраны"
    region_text = REGION_LABEL.get(region_key, region_key)
    threshold_text = THRESHOLD_LABEL.get(threshold, threshold)
    return (
        "<b>Текущие настройки</b>\n"
        f"Отрасли: {industries_text}\n"
        f"Регионы: {region_text}\n"
        f"Порог: {threshold_text}"
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    user = await crud.get_user(session, message.from_user.id)
    if user is None:
        user = await crud.add_user(session, message.from_user.id, message.from_user.username)

    selected_industries = _extract_industries_from_okveds(user.selected_okveds)
    selected_region_raw = user.selected_regions[0] if user.selected_regions else "all"
    selected_region = REGION_KEY_BY_LABEL.get(selected_region_raw, selected_region_raw)
    threshold = user.risk_threshold or "medium"

    await state.update_data(
        selected_industries=selected_industries,
        selected_region=selected_region,
        threshold=threshold,
    )
    await state.set_state(OnboardingStates.choosing_industry)

    await message.answer(
        _build_settings_summary(selected_industries, selected_region, threshold)
        + "\n\nВыберите отрасли:",
        reply_markup=get_industries_keyboard(set(selected_industries)),
    )


@router.callback_query(F.data.startswith("industry:"))
async def callback_industry(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if callback.data is None or callback.message is None:
        return

    action = callback.data.split(":", maxsplit=1)[1]
    data = await state.get_data()
    selected_industries: list[str] = list(data.get("selected_industries", []))

    if action == "done":
        if not selected_industries:
            await callback.answer("Выберите хотя бы одну отрасль", show_alert=True)
            return

        selected_region = data.get("selected_region", "all")
        await state.set_state(OnboardingStates.choosing_region)
        await callback.message.edit_text(
            "Выберите регион (или все регионы):",
            reply_markup=get_regions_keyboard(selected_region),
        )
        await callback.answer()
        return

    if action in selected_industries:
        selected_industries.remove(action)
    else:
        selected_industries.append(action)

    await state.update_data(selected_industries=selected_industries)
    await callback.message.edit_reply_markup(
        reply_markup=get_industries_keyboard(set(selected_industries)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("region:"))
async def callback_region(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data is None or callback.message is None:
        return

    region = callback.data.split(":", maxsplit=1)[1]
    await state.update_data(selected_region=region)
    data = await state.get_data()

    threshold = data.get("threshold", "medium")
    await state.set_state(OnboardingStates.choosing_threshold)
    await callback.message.edit_text(
        "Выберите минимальный уровень риска для уведомлений:",
        reply_markup=get_threshold_keyboard(threshold),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("threshold:"))
async def callback_threshold(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.data is None or callback.message is None or callback.from_user is None:
        return

    threshold = callback.data.split(":", maxsplit=1)[1]
    if threshold not in {"low", "medium", "high"}:
        await callback.answer("Некорректный порог", show_alert=True)
        return

    data = await state.get_data()
    selected_industries: list[str] = list(data.get("selected_industries", []))
    selected_region: str = data.get("selected_region", "all")

    okveds: list[str] = []
    seen: set[str] = set()
    for industry in selected_industries:
        for code in INDUSTRY_TO_OKVED.get(industry, []):
            if code not in seen:
                seen.add(code)
                okveds.append(code)

    regions = [] if selected_region == "all" else [REGION_LABEL.get(selected_region, selected_region)]

    await crud.update_user_settings(
        session=session,
        telegram_id=callback.from_user.id,
        okveds=okveds,
        regions=regions,
        threshold=threshold,
    )

    await state.clear()
    await callback.message.edit_text(
        "✅ Настройки обновлены\n\n"
        + _build_settings_summary(selected_industries, selected_region, threshold)
    )
    await callback.answer("Сохранено")
