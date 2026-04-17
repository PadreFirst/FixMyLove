from __future__ import annotations
import logging
from typing import Any

from ai.diagnostics import run_diagnostics
from ai.response import generate_session_response
from ai.gemini import generate
from ai.prompts import FAREWELL_PROMPT, build_user_data_block, build_sliding_window_block
from db.operations import (
    get_user,
    get_last_messages,
    get_last_summaries,
    update_dynamic,
    update_dynamic_field,
    open_new_session,
    push_to_sliding_window,
    update_last_message_time,
)
from utils.constants import MessageType

logger = logging.getLogger(__name__)

MIN_MESSAGES_PER_PHASE = 3


async def handle_session_message(
    user_id: str,
    user_message: str,
    user: dict[str, Any],
) -> str:
    """Process a session-type message through Blocks A-K."""
    dynamic = user.get("dynamic", {})
    session_open = dynamic.get("session_open", False)

    last_msgs = await get_last_messages(user_id, 3)
    detected_patterns = user.get("detected_patterns", [])

    diag = await run_diagnostics(user_message, last_msgs, detected_patterns, dynamic)

    if diag.get("crisis_markers", {}).get("suicidal"):
        from services.crisis import handle_crisis
        return await handle_crisis(user_id, user_message, user, "suicidal")
    if diag.get("crisis_markers", {}).get("abuse"):
        from services.crisis import handle_crisis
        return await handle_crisis(user_id, user_message, user, "abuse")

    is_new = diag.get("is_new_session", True) or not session_open

    if is_new:
        return await _handle_new_session(user_id, user_message, user, diag)
    else:
        return await _handle_existing_session(user_id, user_message, user, diag)


async def _handle_new_session(
    user_id: str,
    user_message: str,
    user: dict[str, Any],
    diag: dict[str, Any],
) -> str:
    """Blocks A-G for a new session."""
    old_dynamic = user.get("dynamic", {})
    if old_dynamic.get("session_open"):
        from services.summarizer import summarize_and_close_session
        window = old_dynamic.get("sliding_window", [])
        await summarize_and_close_session(user_id, window, old_dynamic)

    session_id = await open_new_session(user_id)

    updates = {
        "session_open": True,
        "session_id": session_id,
        "situation_type": diag.get("situation_type", "chronic"),
        "user_goal": diag.get("user_goal", "understand"),
        "initiator": diag.get("initiator", "unclear"),
        "dominant_pattern": diag.get("dominant_pattern", "undefined"),
        "tone": diag.get("tone", "analytical"),
        "is_acute": diag.get("situation_type") == "acute",
        "current_request": user_message[:200],
    }

    if diag.get("situation_type") == "acute":
        updates["current_phase"] = "validation"
    elif diag.get("needs_more_context"):
        updates["current_phase"] = "validation"
    else:
        updates["current_phase"] = "mapping"

    status = user.get("relationship_status", "")
    if status == "ищу":
        updates["current_phase"] = "validation"
        updates["dominant_pattern"] = "undefined"

    pattern = diag.get("dominant_pattern", "undefined")
    updates["methodology"] = _get_methodology_name(pattern)

    await update_dynamic(user_id, updates)
    await push_to_sliding_window(user_id, "user", user_message)
    await update_last_message_time(user_id)

    summaries = await get_last_summaries(user_id, 3)
    model_key = diag.get("model_to_use", "flash_thinking_2000")

    pending_task = ""
    if summaries:
        last_summary = summaries[-1]
        pending_task = last_summary.get("pending_task", "")
        if pending_task and pending_task != "-":
            user_message_with_context = (
                f"[КОНТЕКСТ: В прошлой сессии пользователь взял задание: {pending_task}]\n\n"
                f"{user_message}"
            )
        else:
            user_message_with_context = user_message
    else:
        user_message_with_context = user_message

    updated_user = await get_user(user_id)
    updated_dynamic = updated_user.get("dynamic", {}) if updated_user else updates

    response = await generate_session_response(
        user_message=user_message_with_context,
        user=user,
        dynamic=updated_dynamic,
        model_key=model_key,
        summaries=summaries,
    )

    await push_to_sliding_window(user_id, "bot", response)
    await update_dynamic_field(user_id, "session_message_count", 1)
    return response


async def _handle_existing_session(
    user_id: str,
    user_message: str,
    user: dict[str, Any],
    diag: dict[str, Any],
) -> str:
    """Blocks H-K for existing session."""
    dynamic = user.get("dynamic", {})

    if diag.get("session_end_detected"):
        await push_to_sliding_window(user_id, "user", user_message)
        updated = await get_user(user_id)
        farewell = await _generate_farewell(user_id, user_message, updated)
        if farewell:
            await push_to_sliding_window(user_id, "bot", farewell)
        from services.summarizer import summarize_and_close_session
        updated = await get_user(user_id)
        if updated:
            dyn = updated.get("dynamic", {})
            window = dyn.get("sliding_window", [])
            await summarize_and_close_session(user_id, window, dyn)
        return farewell or "Спасибо за сессию. Я рядом — пиши когда будешь готов."

    phase_updates = {}

    if dynamic.get("is_acute") and diag.get("situation_type") != "acute":
        phase_updates["is_acute"] = False
        phase_updates["tone"] = "analytical"

    new_pattern = diag.get("dominant_pattern", "")
    if (
        new_pattern
        and new_pattern != "undefined"
        and new_pattern != dynamic.get("dominant_pattern")
        and diag.get("pattern_confidence") in ("high", "medium")
    ):
        phase_updates["dominant_pattern"] = new_pattern
        phase_updates["methodology"] = _get_methodology_name(new_pattern)

    if phase_updates:
        await update_dynamic(user_id, phase_updates)

    await push_to_sliding_window(user_id, "user", user_message)
    await update_last_message_time(user_id)

    updated_user = await get_user(user_id)
    if not updated_user:
        return "Что-то пошло не так на моей стороне. Подожди немного и попробуй ещё раз."

    updated_dynamic = updated_user.get("dynamic", {})
    window = updated_dynamic.get("sliding_window", [])
    model_key = diag.get("model_to_use", "flash_thinking_2000")

    summaries = None
    from datetime import datetime, timezone, timedelta
    last_time = dynamic.get("last_message_time")
    if last_time:
        if isinstance(last_time, str):
            try:
                last_time = datetime.fromisoformat(last_time)
            except ValueError:
                last_time = None
        if last_time:
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - last_time) > timedelta(hours=24):
                summaries = await get_last_summaries(user_id, 3)

    response = await generate_session_response(
        user_message=user_message,
        user=updated_user,
        dynamic=updated_dynamic,
        model_key=model_key,
        summaries=summaries,
        window=window,
    )

    await push_to_sliding_window(user_id, "bot", response)

    phase_msg_count = updated_dynamic.get("phase_message_count", 0) + 1
    await update_dynamic_field(user_id, "phase_message_count", phase_msg_count)

    session_msg_count = updated_dynamic.get("session_message_count", 0) + 1
    await update_dynamic_field(user_id, "session_message_count", session_msg_count)

    current_phase = updated_dynamic.get("current_phase", "validation")
    if phase_msg_count >= MIN_MESSAGES_PER_PHASE:
        next_phase = _maybe_advance_phase(current_phase, diag)
        if next_phase and next_phase != current_phase:
            await update_dynamic_field(user_id, "current_phase", next_phase)
            await update_dynamic_field(user_id, "phase_message_count", 0)

    return response


async def _generate_farewell(
    user_id: str,
    user_message: str,
    user: dict[str, Any] | None,
) -> str:
    """Generate a warm farewell message when the session closes."""
    if not user:
        return ""
    dynamic = user.get("dynamic", {})
    window = dynamic.get("sliding_window", [])

    context_parts = [build_user_data_block(user)]
    if window:
        context_parts.append(build_sliding_window_block(window[-8:]))
    context_parts.append(f"Паттерн: {dynamic.get('dominant_pattern', 'не определён')}")
    context_parts.append(f"Фаза: {dynamic.get('current_phase', '?')}")

    context = "\n".join(context_parts)
    try:
        return await generate(
            system_prompt=FAREWELL_PROMPT,
            user_message=f"{context}\n\nПоследнее сообщение пользователя:\n{user_message}",
            model_key="flash",
        )
    except Exception as e:
        logger.error("Farewell generation error: %s", e)
        return ""


def _get_methodology_name(pattern: str) -> str:
    mapping = {
        "pursue_withdraw": "Pursue-Withdraw",
        "stonewalling": "Stonewalling",
        "passive_aggression": "Пассивная агрессия",
        "intermittent": "Интермиттентное подкрепление",
        "contempt": "Contempt (презрение)",
        "defensiveness": "Defensiveness (защитная реакция)",
        "undefined": "Базовый алгоритм",
    }
    return mapping.get(pattern, "Базовый алгоритм")


def _maybe_advance_phase(current_phase: str, diag: dict[str, Any]) -> str | None:
    """Determine if we should advance to the next phase."""
    phase_order = [
        "validation", "mapping", "roots",
        "partner_perspective", "agency", "trainer",
    ]

    if current_phase not in phase_order:
        return None

    idx = phase_order.index(current_phase)
    if idx < len(phase_order) - 1:
        return phase_order[idx + 1]

    return None
