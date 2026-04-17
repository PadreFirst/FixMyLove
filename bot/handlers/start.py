from __future__ import annotations
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from bot.keyboards import (
    relationship_status_keyboard,
    attachment_question_keyboard,
    diary_offer_keyboard,
)
from db.operations import (
    get_or_create_user,
    update_user,
    update_static_field,
    get_last_summaries,
)
from services.onboarding import (
    onboarding_state,
    get_step_message,
    get_step_reprompt,
    process_onboarding_answer,
)
from utils.constants import ONBOARDING_WELCOME
from utils.typing_keeper import TypingKeeper

logger = logging.getLogger(__name__)
router = Router()


# In-memory flag: user clicked "write free-form" on a callback step
# {user_id: step_name}  — step_name is "relationship_status" or "att_qN"
_freeform_pending: dict[str, str] = {}


async def _typing(message: Message):
    try:
        from aiogram.enums import ChatAction
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    except Exception:
        pass


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    await _typing(message)
    user = await get_or_create_user(user_id)

    if user.get("onboarding_complete"):
        await _send_returning_user_greeting(message, user_id, user)
        return

    current_step = onboarding_state.current_step(user_id)
    if current_step:
        await message.answer(
            "Продолжаем с того же места 👇",
        )
        await _send_onboarding_step(message, user_id, current_step)
        return

    await update_static_field(user_id, "privacy_accepted", True)
    onboarding_state.start(user_id)
    await message.answer(ONBOARDING_WELCOME)


async def _send_returning_user_greeting(message: Message, user_id: str, user: dict):
    """Warm, personalised greeting for returning users."""
    name = user.get("name") or ""
    summaries = await get_last_summaries(user_id, 1)
    pending_task = ""
    last_insight = ""
    if summaries:
        last = summaries[-1]
        pending_task = (last.get("pending_task") or "").strip()
        last_insight = (last.get("key_insight") or "").strip()

    hello = f"С возвращением, {name}!" if name else "С возвращением!"

    if pending_task and pending_task != "-":
        body = (
            f"В прошлый раз мы договорились попробовать: {pending_task}\n\n"
            "Получилось? Или хочется обсудить что-то другое?"
        )
    elif last_insight:
        body = (
            f"Помню, в прошлый раз мы остановились на том, что {last_insight.lower()}\n\n"
            "Что сейчас актуально — продолжим или есть новый вопрос?"
        )
    else:
        body = "Расскажи, что сейчас беспокоит — с чего хочешь начать?"

    await message.answer(f"{hello} {body}")


@router.callback_query(F.data.startswith("rel_"))
async def relationship_status_handler(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    await callback.answer()
    await _typing(callback.message)

    if callback.data == "rel_other":
        _freeform_pending[user_id] = "relationship_status"
        await callback.message.answer(
            "Напиши своими словами — в двух-трёх словах. Например: «встречаемся, но тяжело», "
            "«в разводе», «в свободных отношениях»."
        )
        return

    mapping = {
        "rel_yes": "Да, в отношениях",
        "rel_broke_up": "Нет, расстались",
        "rel_looking": "Ищу",
    }
    answer_text = mapping.get(callback.data, "Да")
    _freeform_pending.pop(user_id, None)

    await _process_step_and_advance(callback.message, user_id, "relationship_status", answer_text)


@router.callback_query(F.data.startswith("att_"))
async def attachment_answer_handler(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    await callback.answer()
    await _typing(callback.message)

    if callback.data.startswith("att_free_"):
        try:
            idx = int(callback.data.split("_")[-1])
        except ValueError:
            idx = 0
        step = f"att_q{idx + 1}"
        _freeform_pending[user_id] = step
        await callback.message.answer(
            "Опиши своими словами — одним-двумя предложениями, как ты обычно поступаешь в такой ситуации."
        )
        return

    parts = callback.data.split("_")
    if len(parts) >= 3:
        letter = parts[2]
        onboarding_state.add_attachment_answer(user_id, letter)

    _freeform_pending.pop(user_id, None)
    onboarding_state.advance(user_id)
    step = onboarding_state.current_step(user_id)
    if step:
        await _send_onboarding_step(callback.message, user_id, step)
    else:
        await _finish_onboarding(callback.message, user_id)


@router.callback_query(F.data.in_({"diary_yes", "diary_no"}))
async def diary_offer_handler(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    await callback.answer()
    await _typing(callback.message)

    if callback.data == "diary_yes":
        await update_static_field(user_id, "diary_enabled", True)
        await callback.message.answer(
            "Напиши в какие дни и время тебе удобно (по Москве) — в свободной форме, "
            "например: «по вторникам в 19:00»."
        )
        onboarding_state.insert_steps_after_current(user_id, ["diary_schedule"])
        onboarding_state.advance(user_id)
    else:
        await update_static_field(user_id, "diary_enabled", False)
        onboarding_state.advance(user_id)
        step = onboarding_state.current_step(user_id)
        if step:
            await _send_onboarding_step(callback.message, user_id, step)
        else:
            await _finish_onboarding(callback.message, user_id)


async def handle_onboarding_text(message: Message) -> bool:
    """Handle text messages during onboarding.

    Returns True if message was consumed by onboarding, False otherwise.
    """
    user_id = str(message.from_user.id)
    step = onboarding_state.current_step(user_id)

    if step is None:
        user = await get_or_create_user(user_id)
        if not user.get("onboarding_complete"):
            onboarding_state.start(user_id)
            step = onboarding_state.current_step(user_id)
            if step:
                await _typing(message)
                await _send_onboarding_step(message, user_id, step)
                return True
        return False

    from utils.text import has_crisis_markers
    if has_crisis_markers(message.text or ""):
        return False

    # If user previously clicked "write free-form" on a callback-only step —
    # route current text to that step instead of the text-stage step.
    pending = _freeform_pending.get(user_id)
    if pending and pending == step:
        _freeform_pending.pop(user_id, None)

    async with TypingKeeper(message.bot, message.chat.id):
        await _process_step_and_advance(message, user_id, step, message.text or "")
    return True


async def _process_step_and_advance(
    message: Message, user_id: str, step: str, text: str
):
    user = await get_or_create_user(user_id)
    result = await process_onboarding_answer(user_id, step, text, user)

    if not result.get("valid"):
        # Soft re-prompt — keep the same step, don't advance
        await message.answer(get_step_reprompt(step))
        if step.startswith("att_q"):
            try:
                idx = int(step[-1]) - 1
            except ValueError:
                idx = 0
            await message.answer(
                "Можешь выбрать вариант кнопкой или написать своими словами:",
                reply_markup=attachment_question_keyboard(idx),
            )
        elif step == "relationship_status":
            await message.answer(
                "Или выбери кнопкой:",
                reply_markup=relationship_status_keyboard(),
            )
        return

    if result.get("attachment_letter"):
        onboarding_state.add_attachment_answer(user_id, result["attachment_letter"])

    if result.get("next_steps"):
        onboarding_state.insert_steps_after_current(user_id, result["next_steps"])

    onboarding_state.advance(user_id)
    next_step = onboarding_state.current_step(user_id)

    if next_step:
        await _send_onboarding_step(message, user_id, next_step)
    else:
        await _finish_onboarding(message, user_id)


async def _send_onboarding_step(message: Message, user_id: str, step: str):
    if step == "relationship_status":
        await message.answer(
            "Ты сейчас в отношениях?\n\n"
            "Выбери вариант — или напиши своими словами, если ни один не подходит.",
            reply_markup=relationship_status_keyboard(),
        )
        return

    if step.startswith("att_q"):
        idx = int(step[-1]) - 1
        text = get_step_message(step)
        kb = attachment_question_keyboard(idx)
        if text:
            await message.answer(text, reply_markup=kb)
        return

    if step == "diary_offer":
        text = get_step_message(step)
        if text:
            await message.answer(text, reply_markup=diary_offer_keyboard())
        return

    text = get_step_message(step)
    if text:
        await message.answer(text)


async def _finish_onboarding(message: Message, user_id: str):
    attachment = onboarding_state.compute_attachment_style(user_id)
    await update_user(user_id, {
        "attachment_style": attachment.value,
        "onboarding_complete": True,
    })
    onboarding_state.cleanup(user_id)

    user = await get_or_create_user(user_id)
    name = user.get("name", "")
    greeting = f"Отлично, {name}!" if name else "Отлично!"
    await message.answer(
        f"{greeting} Теперь я знаю тебя немного лучше.\n\n"
        "Расскажи — что тебя беспокоит прямо сейчас? Можно подробно или в двух словах — как удобно."
    )
