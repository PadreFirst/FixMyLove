from __future__ import annotations
import logging
from typing import Any

from ai.gemini import generate
from ai.prompts import (
    build_full_system_prompt,
    build_user_data_block,
    CRISIS_SUICIDE_PROMPT,
    CRISIS_ABUSE_PROMPT,
)

logger = logging.getLogger(__name__)


async def generate_session_response(
    user_message: str,
    user: dict[str, Any],
    dynamic: dict[str, Any],
    model_key: str,
    summaries: list[dict[str, Any]] | None = None,
    window: list[dict[str, str]] | None = None,
) -> str:
    """Steps 7-8: build prompt and generate response."""
    system_prompt = build_full_system_prompt(user, dynamic, summaries, window)

    try:
        return await generate(
            system_prompt=system_prompt,
            user_message=user_message,
            model_key=model_key,
        )
    except Exception as e:
        logger.error("Response generation error: %s", e)
        return "Что-то пошло не так на моей стороне. Подожди немного и попробуй ещё раз."


async def generate_crisis_response(
    user_message: str,
    user: dict[str, Any],
    crisis_type: str,
    last_messages: list[dict[str, str]] | None = None,
) -> str:
    """Generate crisis response (suicide or abuse)."""
    user_block = build_user_data_block(user)

    if crisis_type == "suicidal":
        prompt = CRISIS_SUICIDE_PROMPT.format(user_data_block=user_block)
    else:
        prompt = CRISIS_ABUSE_PROMPT.format(user_data_block=user_block)

    context = ""
    if last_messages:
        history = "\n".join(
            f"{m.get('role', '?')}: {m.get('text', '')}" for m in last_messages[-10:]
        )
        context = f"Контекст диалога:\n{history}\n\n"

    try:
        return await generate(
            system_prompt=prompt,
            user_message=f"{context}Сообщение пользователя:\n{user_message}",
            model_key="pro",
        )
    except Exception as e:
        logger.error("Crisis response error: %s", e)
        if crisis_type == "suicidal":
            return (
                "Слышу что тебе сейчас очень тяжело. "
                "Сейчас важнее всего поговорить с живым человеком:\n"
                "8-800-100-49-94 — телефон доверия, круглосуточно, бесплатно\n"
                "8-800-333-44-34 — кризисная линия доверия\n\n"
                "Я здесь. Ты не один."
            )
        return (
            "Слышу что происходит что-то серьёзное. "
            "Вот контакт людей которые могут помочь прямо сейчас:\n"
            "8-800-7000-600 — кризисный центр «Анна», круглосуточно\n\n"
            "Я рядом — расскажи что происходит."
        )


async def generate_trainer_response(
    user_message: str,
    user: dict[str, Any],
    dynamic: dict[str, Any],
    window: list[dict[str, str]] | None = None,
) -> str:
    """Generate trainer (formulation practice) response."""
    system_prompt = build_full_system_prompt(user, dynamic, window=window)
    system_prompt += """

[РЕЖИМ ТРЕНАЖЁРА]
Пользователь тренирует формулировку для разговора с партнёром.
1. Разбери формулировку: где переход на личности? Где обвинение вместо потребности? Где хорошо?
2. Дай обратную связь по структуре.
3. Предложи переформулировку если нужно.
4. Один открытый вопрос в конце."""

    try:
        return await generate(
            system_prompt=system_prompt,
            user_message=user_message,
            model_key="flash",
        )
    except Exception as e:
        logger.error("Trainer response error: %s", e)
        return "Что-то пошло не так на моей стороне. Подожди немного и попробуй ещё раз."


async def generate_reflection_response(
    user_message: str,
    user: dict[str, Any],
    summaries: list[dict[str, Any]],
    mood_history: list[int | None],
    detected_patterns: list[str],
) -> str:
    """Generate reflection/dynamics response."""
    system = """Ты — психолог. Пользователь просит рефлексию — обзор динамики отношений за период.

Задача:
1. Формируй картину динамики: что изменилось, какие паттерны повторяются, куда движется.
2. Дай обратную связь.
3. Один открытый вопрос в конце.

Будь конкретен — ссылайся на конкретные сессии и изменения."""

    context_parts = [build_user_data_block(user)]

    if summaries:
        context_parts.append("Все сессии:")
        for s in summaries:
            context_parts.append(
                f"  {s.get('date', '?')}: {s.get('user_request', '?')} | "
                f"Паттерн: {s.get('dominant_pattern', '?')} | "
                f"Действие: {s.get('user_action', '?')} | "
                f"Настроение: {s.get('mood_in', '?')}→{s.get('mood_out', '?')}"
            )

    if mood_history:
        context_parts.append(f"История настроения: {mood_history}")
    if detected_patterns:
        context_parts.append(f"Выявленные паттерны: {', '.join(detected_patterns)}")

    context = "\n".join(context_parts)

    model_key = "pro" if len(summaries) > 10 else "flash_thinking_2000"

    try:
        return await generate(
            system_prompt=system,
            user_message=f"{context}\n\nЗапрос пользователя:\n{user_message}",
            model_key=model_key,
        )
    except Exception as e:
        logger.error("Reflection error: %s", e)
        return "Что-то пошло не так на моей стороне. Подожди немного и попробуй ещё раз."


async def generate_off_topic_response(
    user_message: str,
    is_first_off_topic: bool,
    in_active_session: bool,
    current_topic: str = "",
) -> str:
    """Generate off-topic response."""
    if in_active_session:
        return f"Давай вернёмся к тому о чём говорили — {current_topic}" if current_topic else (
            "Давай вернёмся к нашему разговору. О чём ты хотел продолжить?"
        )

    if is_first_off_topic:
        system = (
            "Ты — психолог по отношениям. Пользователь задал вопрос не про отношения. "
            "Коротко ответь на вопрос, затем мягко добавь: "
            "'Я здесь прежде всего для работы с отношениями — если захочешь разобрать ситуацию, пиши.'"
        )
        try:
            return await generate(
                system_prompt=system,
                user_message=user_message,
                model_key="flash",
            )
        except Exception:
            return "Я здесь прежде всего для работы с отношениями — если захочешь разобрать ситуацию, пиши."
    else:
        return "Я здесь для работы с отношениями. Есть что-то что хочешь разобрать?"


async def generate_admin_response(
    user_message: str,
) -> str:
    """Generate admin/settings response."""
    system = (
        "Пользователь хочет изменить настройки. Определи что именно он хочет изменить "
        "и подтверди изменение коротко. Если непонятно — уточни одним вопросом."
    )
    try:
        return await generate(
            system_prompt=system,
            user_message=user_message,
            model_key="flash",
        )
    except Exception:
        return "Что именно ты хочешь изменить?"
