from __future__ import annotations
import io
import logging

from aiogram import Router, F, Bot
from aiogram.enums import ChatAction
from aiogram.types import Message

from config import ADMIN_USER_IDS, RESET_PHRASE
from db.operations import get_or_create_user, delete_user
from services.pipeline import process_message
from bot.handlers.start import handle_onboarding_text
from services.onboarding import onboarding_state
from ai.gemini import transcribe_voice

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot):
    """Step 1: normalize voice → text, then process."""
    user_id = str(message.from_user.id)
    user = await get_or_create_user(user_id)

    if not user.get("onboarding_complete"):
        await message.answer("Давай сначала познакомимся — напиши /start")
        return

    await message.answer_chat_action(ChatAction.TYPING)
    try:
        file = await bot.get_file(message.voice.file_id)
        data = io.BytesIO()
        await bot.download_file(file.file_path, data)
        audio_bytes = data.getvalue()

        text = await transcribe_voice(audio_bytes)
        if not text:
            await message.answer("Не удалось распознать голосовое сообщение. Попробуй написать текстом.")
            return

        text = f"[голосовое сообщение] {text}"
    except Exception as e:
        logger.error("Voice processing error: %s", e)
        await message.answer("Не удалось обработать голосовое. Попробуй написать текстом.")
        return

    response = await process_message(user_id, text)
    if response:
        await message.answer(response, parse_mode="HTML")


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot):
    """Step 1: normalize photo → pass with tag."""
    user_id = str(message.from_user.id)
    user = await get_or_create_user(user_id)

    if not user.get("onboarding_complete"):
        await message.answer("Давай сначала познакомимся — напиши /start")
        return

    await message.answer_chat_action(ChatAction.TYPING)
    caption = message.caption or ""
    text = f"[скриншот переписки] {caption}".strip()

    response = await process_message(user_id, text)
    if response:
        await message.answer(response, parse_mode="HTML")


@router.message(F.text)
async def handle_text(message: Message):
    """Main text message handler."""
    user_id = str(message.from_user.id)
    text = (message.text or "").strip()

    if text == RESET_PHRASE and user_id in ADMIN_USER_IDS:
        await delete_user(user_id)
        onboarding_state.cleanup(user_id)
        logger.info("Admin %s triggered full reset", user_id)
        await message.answer("Профиль полностью удалён. Напиши /start чтобы начать с нуля.")
        return

    user = await get_or_create_user(user_id)

    if not user.get("onboarding_complete"):
        consumed = await handle_onboarding_text(message)
        if consumed:
            return
        from utils.text import has_crisis_markers
        if has_crisis_markers(message.text or ""):
            from services.crisis import handle_crisis
            response = await handle_crisis(user_id, message.text, user, "suicidal")
            if response:
                await message.answer(response, parse_mode="HTML")
            return
        await message.answer("Давай сначала познакомимся — напиши /start")
        return

    await message.answer_chat_action(ChatAction.TYPING)
    response = await process_message(user_id, message.text or "")
    if response:
        await message.answer(response, parse_mode="HTML")
