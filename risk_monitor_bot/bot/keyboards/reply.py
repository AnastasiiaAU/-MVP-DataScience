from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/risks"), KeyboardButton(text="/settings")],
            [KeyboardButton(text="/subscribe"), KeyboardButton(text="/unsubscribe")],
        ],
        resize_keyboard=True,
    )
