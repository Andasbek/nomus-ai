"""Inline-клавиатуры."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def disclaimer_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Понятно", callback_data="ack_disclaimer")]]
    )


def citizenship_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🇺🇿 Узбекистан", callback_data="cit:UZ")],
        [InlineKeyboardButton(text="🇰🇬 Кыргызстан", callback_data="cit:KG")],
        [InlineKeyboardButton(text="🇹🇯 Таджикистан", callback_data="cit:TJ")],
        [InlineKeyboardButton(text="🌍 Другое", callback_data="cit:OTHER")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def yes_no_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"{prefix}:yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"{prefix}:no"),
                InlineKeyboardButton(text="🤷 Не знаю", callback_data=f"{prefix}:unknown"),
            ]
        ]
    )


def answer_kb(offer_document: str | None) -> InlineKeyboardMarkup:
    rows = []
    if offer_document == "labor_inspection_claim":
        rows.append(
            [InlineKeyboardButton(text="📄 Сформировать заявление", callback_data="make_claim")]
        )
    rows.append([InlineKeyboardButton(text="🧑‍⚖️ Нужен живой юрист", callback_data="need_lawyer")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lawyer_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧑‍⚖️ Нужен живой юрист", callback_data="need_lawyer")]
        ]
    )
