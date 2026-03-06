from __future__ import annotations
import logging
from typing import Any

from aiogram import Router, F
from aiogram.enums import ChatAction
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from bot.keyboards import (
    relationship_status_keyboard,
    attachment_question_keyboard,
    diary_offer_keyboard,
)
from db.operations import get_or_create_user, update_user, update_static_field
from services.onboarding import (
    onboarding_state,
    get_step_message,
    process_onboarding_answer,
)
from utils.constants import ONBOARDING_WELCOME

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    await message.answer_chat_action(ChatAction.TYPING)
    user = await get_or_create_user(user_id)

    if user.get("onboarding_complete"):
        await message.answer("С возвращением! Расскажи что тебя беспокоит.")
        return

    await update_static_field(user_id, "privacy_accepted", True)
    onboarding_state.start(user_id)
    await message.answer(ONBOARDING_WELCOME)


@router.callback_query(F.data.startswith("rel_"))
async def relationship_status_handler(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    await callback.answer()
    await callback.message.answer_chat_action(ChatAction.TYPING)

    mapping = {
        "rel_yes": "Да",
        "rel_broke_up": "Нет, расстались",
        "rel_looking": "Ищу",
    }
    answer_text = mapping.get(callback.data, "Да")

    await _process_step_and_advance(callback.message, user_id, "relationship_status", answer_text)


@router.callback_query(F.data.startswith("att_"))
async def attachment_answer_handler(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    await callback.answer()
    await callback.message.answer_chat_action(ChatAction.TYPING)

    parts = callback.data.split("_")
    if len(parts) >= 3:
        letter = parts[2]
        onboarding_state.add_attachment_answer(user_id, letter)

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
    await callback.message.answer_chat_action(ChatAction.TYPING)

    if callback.data == "diary_yes":
        await update_static_field(user_id, "diary_enabled", True)
        await callback.message.answer("Напиши в какие дни и время тебе удобно (по Москве)")
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
                await message.answer_chat_action(ChatAction.TYPING)
                await _send_onboarding_step(message, user_id, step)
                return True
        return False

    from utils.text import has_crisis_markers
    if has_crisis_markers(message.text or ""):
        return False

    await message.answer_chat_action(ChatAction.TYPING)
    await _process_step_and_advance(message, user_id, step, message.text or "")
    return True


async def _process_step_and_advance(
    message: Message, user_id: str, step: str, text: str
):
    user = await get_or_create_user(user_id)
    result = await process_onboarding_answer(user_id, step, text, user)

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
            "Ты сейчас в отношениях?",
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
        "Расскажи — что тебя беспокоит прямо сейчас?"
    )
