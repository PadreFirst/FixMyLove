from __future__ import annotations
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.keyboards import delete_data_confirm_keyboard
from db.operations import delete_user, get_or_create_user
from services.diary import handle_diary_show, handle_diary_update

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("diary"))
async def cmd_diary(message: Message):
    user_id = str(message.from_user.id)
    text = message.text or ""

    if "show" in text.lower():
        response = await handle_diary_show(user_id, text)
    else:
        rest = text.replace("/diary", "").strip()
        if rest:
            response = await handle_diary_update(user_id, rest)
        else:
            response = (
                "Команды дневника:\n"
                "/diary show — показать последние записи\n"
                "/diary show 20 — показать 20 последних записей\n"
                "/diary <текст> — добавить запись\n\n"
                "Или просто напиши «запиши в дневник» + текст."
            )

    await message.answer(response, parse_mode="HTML")


@router.message(Command("delete_data"))
async def cmd_delete_data(message: Message):
    await message.answer(
        "Ты уверен? Это удалит все твои данные — профиль, историю, дневник. Отменить нельзя.",
        reply_markup=delete_data_confirm_keyboard(),
    )


@router.callback_query(lambda c: c.data == "delete_confirm")
async def delete_confirmed(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    await delete_user(user_id)
    await callback.answer("Данные удалены.")
    await callback.message.answer(
        "Все данные удалены. Если захочешь начать заново — напиши /start."
    )


@router.callback_query(lambda c: c.data == "delete_cancel")
async def delete_cancelled(callback: CallbackQuery):
    await callback.answer("Отменено.")
    await callback.message.answer("Ок, ничего не удаляю. Продолжаем.")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    user_id = str(message.from_user.id)
    user = await get_or_create_user(user_id)

    name = user.get("name", "не указано")
    age = user.get("age", "не указано")
    partner = user.get("partner_name", "не указано")
    status = user.get("relationship_status", "не указано")
    diary = "включён" if user.get("diary_enabled") else "выключен"
    schedule = user.get("diary_schedule", "не задано")

    await message.answer(
        f"<b>Твой профиль:</b>\n"
        f"Имя: {name}\n"
        f"Возраст: {age}\n"
        f"Партнёр: {partner}\n"
        f"Статус: {status}\n"
        f"Дневник: {diary}\n"
        f"Расписание: {schedule}\n\n"
        "Чтобы что-то изменить — просто напиши, например: "
        "«поменяй имя на Маша» или «выключи напоминания».",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Что я умею:</b>\n\n"
        "Просто напиши что тебя беспокоит — и мы начнём разбирать ситуацию.\n\n"
        "<b>Команды:</b>\n"
        "/diary — дневник\n"
        "/diary show — показать записи\n"
        "/settings — твой профиль\n"
        "/delete_data — удалить все данные\n"
        "/help — эта справка",
        parse_mode="HTML",
    )
