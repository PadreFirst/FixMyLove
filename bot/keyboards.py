from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.constants import ATTACHMENT_QUESTIONS


def privacy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Понятно, продолжаем", callback_data="privacy_accept")]
    ])


def welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Давай знакомиться", callback_data="onboarding_start")]
    ])


def relationship_status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data="rel_yes")],
        [InlineKeyboardButton(text="Нет, расстались", callback_data="rel_broke_up")],
        [InlineKeyboardButton(text="Ищу", callback_data="rel_looking")],
    ])


def attachment_question_keyboard(question_index: int) -> InlineKeyboardMarkup:
    if question_index >= len(ATTACHMENT_QUESTIONS):
        return InlineKeyboardMarkup(inline_keyboard=[])

    q = ATTACHMENT_QUESTIONS[question_index]
    buttons = []
    for letter, text in q["options"]:
        buttons.append([
            InlineKeyboardButton(
                text=f"{letter}) {text}",
                callback_data=f"att_{question_index}_{letter}",
            )
        ])
    return buttons_to_keyboard(buttons)


def buttons_to_keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def diary_offer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data="diary_yes"),
            InlineKeyboardButton(text="Нет", callback_data="diary_no"),
        ]
    ])


def delete_data_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, удалить всё", callback_data="delete_confirm"),
            InlineKeyboardButton(text="Отмена", callback_data="delete_cancel"),
        ]
    ])
