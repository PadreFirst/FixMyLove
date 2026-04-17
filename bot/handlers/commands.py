from __future__ import annotations
import logging

from aiogram import Router, F
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.keyboards import reset_confirm_keyboard
from db.operations import get_or_create_user, delete_user
from services.diary import handle_diary_show, handle_diary_update
from services.onboarding import onboarding_state
from services.schedule_parser import schedule_to_human
from utils.text import clean_markdown
from utils.typing_keeper import TypingKeeper

logger = logging.getLogger(__name__)
router = Router()


HELP_TEXT = (
    "<b>Что я умею</b>\n\n"
    "Я — ИИ-помощник по отношениям. Просто напиши что сейчас беспокоит — "
    "разберём вместе. Можно текстом, голосом или скриншотом переписки.\n\n"
    "<b>Команды</b>\n"
    "/start — вернуться к началу / продолжить\n"
    "/menu, /help — эта справка\n"
    "/settings — твой профиль и настройки\n"
    "/diary — добавить запись в дневник\n"
    "/diary show — показать последние записи\n"
    "/reset — начать заново (со сбросом профиля)\n\n"
    "<b>Как это работает</b>\n"
    "— Я помню контекст наших разговоров и возвращаюсь к незавершённому.\n"
    "— Можно писать в свободной форме, даже если предложены кнопки.\n"
    "— Если расстроен моим ответом — напиши «не помогает» или что думаешь. "
    "Я поменяю подход.\n"
    "— Если нужна срочная помощь (кризис): 8-800-100-49-94, круглосуточно, бесплатно."
)


async def _typing(message: Message):
    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    except Exception:
        pass


@router.message(Command("diary"))
async def cmd_diary(message: Message):
    user_id = str(message.from_user.id)
    text = message.text or ""

    async with TypingKeeper(message.bot, message.chat.id):
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

    await message.answer(clean_markdown(response))


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    user_id = str(message.from_user.id)
    await _typing(message)
    user = await get_or_create_user(user_id)

    name = user.get("name", "не указано")
    age = user.get("age", "не указано")
    partner = user.get("partner_name", "не указано")
    status = user.get("relationship_status", "не указано")
    diary = "включён" if user.get("diary_enabled") else "выключен"
    parsed_schedule = user.get("diary_schedule_parsed")
    schedule = schedule_to_human(parsed_schedule) if parsed_schedule else (user.get("diary_schedule") or "не задано")

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
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("reset"))
async def cmd_reset(message: Message):
    await message.answer(
        "Это удалит все твои данные — профиль, историю разговоров, дневник — "
        "и мы начнём с чистого листа. Уверен?",
        reply_markup=reset_confirm_keyboard(),
    )


@router.callback_query(F.data == "reset_confirm")
async def reset_confirm_cb(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    await callback.answer("Сбрасываю…")
    try:
        await delete_user(user_id)
        onboarding_state.cleanup(user_id)
        logger.info("User %s confirmed /reset", user_id)
        await callback.message.answer(
            "Готово — профиль очищен. Напиши /start чтобы познакомиться заново."
        )
    except Exception as e:
        logger.error("Reset error for %s: %s", user_id, e)
        await callback.message.answer("Не получилось сбросить. Попробуй ещё раз позже.")


@router.callback_query(F.data == "reset_cancel")
async def reset_cancel_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Окей, оставляем всё как есть.")
