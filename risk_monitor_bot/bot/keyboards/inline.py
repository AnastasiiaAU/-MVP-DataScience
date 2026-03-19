from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

INDUSTRIES: list[tuple[str, str]] = [
    ("transport", "🚛 Грузоперевозки"),
    ("agriculture", "🌾 Сельское хозяйство"),
    ("construction", "🏗 Строительство"),
    ("trade", "🏪 Торговля"),
    ("manufacturing", "🏭 Производство"),
]

REGIONS: list[tuple[str, str]] = [
    ("all", "🇷🇺 Все регионы"),
    ("cfo", "ЦФО"),
    ("szfo", "СЗФО"),
    ("yfo", "ЮФО"),
    ("pfo", "ПФО"),
    ("ufo", "УФО"),
    ("sfo", "СФО"),
    ("dfo", "ДФО"),
    ("skfo", "СКФО"),
]

THRESHOLDS: list[tuple[str, str]] = [
    ("high", "🔴 Только высокие риски"),
    ("medium", "🟡 Средние и высокие"),
    ("low", "🟢 Все уведомления"),
]


def get_industries_keyboard(selected: set[str] | None = None) -> InlineKeyboardMarkup:
    selected = selected or set()
    builder = InlineKeyboardBuilder()

    for key, title in INDUSTRIES:
        text = f"✅ {title}" if key in selected else title
        builder.button(text=text, callback_data=f"industry:{key}")

    builder.button(text="✅ Готово", callback_data="industry:done")
    builder.adjust(1, 1, 1, 1, 1, 1)
    return builder.as_markup()


def get_regions_keyboard(selected: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for key, title in REGIONS:
        text = f"✅ {title}" if selected == key else title
        builder.button(text=text, callback_data=f"region:{key}")

    builder.adjust(1, 2, 2, 2, 2)
    return builder.as_markup()


def get_threshold_keyboard(selected: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for key, title in THRESHOLDS:
        text = f"✅ {title}" if selected == key else title
        builder.button(text=text, callback_data=f"threshold:{key}")

    builder.adjust(1, 1, 1)
    return builder.as_markup()


def get_risk_detail_keyboard(risk_id: int, source_url: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📄 Подробнее", callback_data=f"risk_detail:{risk_id}")
    builder.button(text="🔗 Источник", url=source_url or "https://t.me")
    builder.adjust(2)
    return builder.as_markup()
