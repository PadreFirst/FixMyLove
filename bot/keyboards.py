from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.constants import ATTACHMENT_QUESTIONS


def relationship_status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, в отношениях", callback_data="rel_yes")],
        [InlineKeyboardButton(text="Нет, расстались", callback_data="rel_broke_up")],
        [InlineKeyboardButton(text="Ищу", callback_data="rel_looking")],
        [InlineKeyboardButton(text="Всё сложно / напишу своими словами", callback_data="rel_other")],
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
    buttons.append([
        InlineKeyboardButton(
            text="✍️ Ответить своими словами",
            callback_data=f"att_free_{question_index}",
        )
    ])
    return buttons_to_keyboard(buttons)


def reset_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, начать заново", callback_data="reset_confirm"),
            InlineKeyboardButton(text="Отмена", callback_data="reset_cancel"),
        ]
    ])


def buttons_to_keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def diary_offer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data="diary_yes"),
            InlineKeyboardButton(text="Нет", callback_data="diary_no"),
        ]
    ])


