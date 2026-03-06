from __future__ import annotations
import json
import logging
from typing import Any

from ai.gemini import generate_json
from ai.prompts import DIAGNOSTICS_PROMPT

logger = logging.getLogger(__name__)

DEFAULT_DIAGNOSTICS = {
    "is_new_session": True,
    "situation_type": "chronic",
    "user_goal": "understand",
    "initiator": "unclear",
    "dominant_pattern": "undefined",
    "pattern_confidence": "low",
    "crisis_markers": {"suicidal": False, "abuse": False},
    "model_to_use": "flash_thinking_2000",
    "session_end_detected": False,
    "tone": "analytical",
    "needs_more_context": True,
}


async def run_diagnostics(
    current_message: str,
    last_messages: list[dict[str, str]],
    detected_patterns: list[str],
    dynamic: dict[str, Any],
) -> dict[str, Any]:
    """Step 6 — run Flash-Lite diagnostics, return JSON."""
    context_parts = []

    if last_messages:
        history = "\n".join(
            f"{m.get('role', '?')}: {m.get('text', '')}" for m in last_messages
        )
        context_parts.append(f"Последние сообщения:\n{history}")

    if detected_patterns:
        context_parts.append(f"Выявленные паттерны: {', '.join(detected_patterns)}")

    if dynamic.get("session_open"):
        context_parts.append(f"Текущий паттерн: {dynamic.get('dominant_pattern', 'не определён')}")
        context_parts.append(f"Тип ситуации: {dynamic.get('situation_type', 'не определён')}")
        context_parts.append(f"Текущая фаза: {dynamic.get('current_phase', 'не определена')}")

    context = "\n".join(context_parts)
    user_msg = f"{context}\n\nНовое сообщение пользователя:\n{current_message}"

    try:
        result = await generate_json(
            system_prompt=DIAGNOSTICS_PROMPT,
            user_message=user_msg,
            model_key="flash_lite",
        )
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        parsed = json.loads(cleaned)

        diag = dict(DEFAULT_DIAGNOSTICS)
        diag.update(parsed)
        return diag
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Diagnostics error: %s. Raw: %s", e, result if 'result' in dir() else "N/A")
        return dict(DEFAULT_DIAGNOSTICS)
