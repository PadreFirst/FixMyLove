from __future__ import annotations
import asyncio
import logging
from typing import Any

from ai.classifier import classify_message
from ai.response import (
    generate_off_topic_response,
    generate_trainer_response,
    generate_reflection_response,
    generate_admin_response,
)
from db.operations import (
    get_or_create_user,
    get_last_messages,
    push_to_sliding_window,
    update_dynamic,
    update_dynamic_field,
    update_last_message_time,
    get_user,
)
from services.crisis import handle_crisis
from services.diary import handle_diary_update, handle_diary_show
from services.session import handle_session_message
from services.summarizer import extract_facts_and_update
from utils.constants import MessageType
from utils.text import has_crisis_markers, is_diary_show_command

logger = logging.getLogger(__name__)


async def process_message(user_id: str, text: str) -> str:
    """Main pipeline — Steps 1-10.

    Step 1 (normalization) is handled by the caller.
    This function starts at Step 2.
    """
    user = await get_or_create_user(user_id)
    dynamic = user.get("dynamic", {})

    if not user.get("onboarding_complete") and not has_crisis_markers(text):
        return ""

    last_msgs = await get_last_messages(user_id, 3)
    detected_patterns = user.get("detected_patterns", [])
    session_open = dynamic.get("session_open", False)
    current_phase = dynamic.get("current_phase", "")

    if is_diary_show_command(text):
        return await handle_diary_show(user_id, text)

    msg_type = await classify_message(
        text, last_msgs, detected_patterns, session_open, current_phase
    )
    logger.info("User %s: message classified as %s", user_id, msg_type.value)

    response = await _route_message(user_id, text, user, dynamic, msg_type)

    if response and msg_type in (MessageType.SESSION, MessageType.TRAINER):
        asyncio.create_task(
            _async_db_update(user_id, text)
        )

    return response


async def _route_message(
    user_id: str,
    text: str,
    user: dict[str, Any],
    dynamic: dict[str, Any],
    msg_type: MessageType,
) -> str:
    """Step 4 — route by message type."""
    if msg_type == MessageType.CRISIS:
        crisis_type = "suicidal" if has_crisis_markers(text) else "abuse"
        return await handle_crisis(user_id, text, user, crisis_type)

    if msg_type == MessageType.DIARY_UPDATE:
        return await handle_diary_update(user_id, text)

    if msg_type == MessageType.OFF_TOPIC:
        off_topic_count = dynamic.get("off_topic_count", 0)
        session_open = dynamic.get("session_open", False)
        current_request = dynamic.get("current_request", "")

        await update_dynamic_field(user_id, "off_topic_count", off_topic_count + 1)

        return await generate_off_topic_response(
            text,
            is_first_off_topic=(off_topic_count == 0),
            in_active_session=session_open,
            current_topic=current_request,
        )

    if msg_type == MessageType.TRAINER:
        window = dynamic.get("sliding_window", [])
        return await generate_trainer_response(text, user, dynamic, window)

    if msg_type == MessageType.REFLECTION:
        summaries = user.get("session_summaries", [])
        mood_history = user.get("mood_history", [])
        detected = user.get("detected_patterns", [])
        return await generate_reflection_response(
            text, user, summaries, mood_history, detected
        )

    if msg_type == MessageType.ADMIN:
        return await generate_admin_response(text)

    if dynamic.get("off_topic_count", 0) > 0:
        await update_dynamic_field(user_id, "off_topic_count", 0)

    return await handle_session_message(user_id, text, user)


async def _async_db_update(user_id: str, current_message: str):
    """Step 10 — asynchronous DB updates after response."""
    try:
        user = await get_user(user_id)
        if not user:
            return
        dynamic = user.get("dynamic", {})
        window = dynamic.get("sliding_window", [])

        result = await extract_facts_and_update(user_id, current_message, window)

        if result.get("session_end_detected"):
            from services.summarizer import summarize_and_close_session
            user = await get_user(user_id)
            if user:
                dyn = user.get("dynamic", {})
                w = dyn.get("sliding_window", [])
                await summarize_and_close_session(user_id, w, dyn)
    except Exception as e:
        logger.error("Async DB update error for user %s: %s", user_id, e)
