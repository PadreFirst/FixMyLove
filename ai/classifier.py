from __future__ import annotations
import logging
from typing import Any

from ai.gemini import generate
from ai.prompts import CLASSIFY_PROMPT
from utils.constants import MessageType
from utils.text import has_crisis_markers, is_diary_command, is_admin_command, is_diary_show_command

logger = logging.getLogger(__name__)


def classify_by_rules(text: str, session_open: bool) -> MessageType | None:
    """Step 3.1 — rule-based classification without LLM."""
    if has_crisis_markers(text):
        return MessageType.CRISIS

    if is_diary_show_command(text):
        return MessageType.DIARY_UPDATE

    if is_diary_command(text):
        return MessageType.DIARY_UPDATE

    if is_admin_command(text):
        return MessageType.ADMIN

    return None


async def classify_by_llm(
    text: str,
    last_messages: list[dict[str, str]],
    detected_patterns: list[str],
    session_open: bool,
    current_phase: str = "",
) -> MessageType:
    """Step 3.2 — LLM classification when rules don't match."""
    context_parts = []

    if last_messages:
        history = "\n".join(
            f"{m.get('role', '?')}: {m.get('text', '')}" for m in last_messages
        )
        context_parts.append(f"Последние сообщения:\n{history}")

    if detected_patterns:
        context_parts.append(f"Выявленные паттерны: {', '.join(detected_patterns)}")

    context_parts.append(f"Сессия открыта: {'да' if session_open else 'нет'}")
    if current_phase:
        context_parts.append(f"Текущая фаза: {current_phase}")

    context = "\n".join(context_parts)
    user_msg = f"{context}\n\nНовое сообщение пользователя:\n{text}"

    try:
        result = await generate(
            system_prompt=CLASSIFY_PROMPT,
            user_message=user_msg,
            model_key="flash_lite",
        )
        result = result.strip().lower()
        type_map = {
            "session": MessageType.SESSION,
            "diary_update": MessageType.DIARY_UPDATE,
            "trainer": MessageType.TRAINER,
            "reflection": MessageType.REFLECTION,
            "admin": MessageType.ADMIN,
            "crisis": MessageType.CRISIS,
            "off_topic": MessageType.OFF_TOPIC,
        }
        return type_map.get(result, MessageType.SESSION)
    except Exception as e:
        logger.error("Classification LLM error: %s", e)
        return MessageType.SESSION


async def classify_message(
    text: str,
    last_messages: list[dict[str, str]],
    detected_patterns: list[str],
    session_open: bool,
    current_phase: str = "",
) -> MessageType:
    """Full Step 3 — classify message type."""
    rule_result = classify_by_rules(text, session_open)
    if rule_result is not None:
        return rule_result

    msg_type = await classify_by_llm(
        text, last_messages, detected_patterns, session_open, current_phase
    )

    if session_open and msg_type == MessageType.TRAINER:
        if current_phase not in ("agency", "trainer"):
            return MessageType.SESSION

    return msg_type
