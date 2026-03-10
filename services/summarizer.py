from __future__ import annotations
import json
import logging
from typing import Any

from ai.gemini import generate_json, generate
from ai.prompts import SUMMARIZE_PROMPT, FACT_EXTRACTION_PROMPT, SHADOW_COMPRESS_PROMPT, DEDUP_FACTS_PROMPT
from db.operations import (
    add_session_summary,
    add_diary_entry,
    close_session,
    update_static_field,
    update_user,
    append_shadow_profile,
    add_important_fact,
    add_session_fact,
    get_user,
)
from config import SHADOW_PROFILE_MAX_SENTENCES, SHADOW_PROFILE_COMPRESS_TO
from utils.text import count_sentences

logger = logging.getLogger(__name__)


async def extract_facts_and_update(
    user_id: str,
    current_message: str,
    window: list[dict[str, str]],
) -> dict[str, Any]:
    """Step 10 — extract facts from dialog and update DB."""
    history = "\n".join(
        f"{m.get('role', '?')}: {m.get('text', '')}" for m in window[-6:]
    )
    user_msg = f"Последние сообщения:\n{history}\n\nТекущее сообщение:\n{current_message}"

    try:
        result = await generate_json(
            system_prompt=FACT_EXTRACTION_PROMPT,
            user_message=user_msg,
            model_key="flash_lite",
        )
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        data = json.loads(cleaned)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Fact extraction error: %s", e)
        return {"session_end_detected": False}

    profile_updates = data.get("profile_updates", {})
    if profile_updates:
        allowed = {
            "name", "age", "partner_name", "partner_age",
            "partner_gender", "relationship_status", "relationship_duration",
            "relationship_note",
        }
        safe_updates = {k: v for k, v in profile_updates.items() if k in allowed and v}
        if safe_updates:
            await update_user(user_id, safe_updates)

    facts = data.get("session_facts", [])
    for fact in facts:
        if fact and fact.strip():
            await add_session_fact(user_id, fact.strip())

    shadow_user = data.get("shadow_user", "")
    shadow_partner = data.get("shadow_partner", "")
    if shadow_user or shadow_partner:
        await append_shadow_profile(user_id, shadow_user, shadow_partner)
        await _maybe_compress_shadow(user_id)

    return data


async def _maybe_compress_shadow(user_id: str):
    """Compress shadow profile if it exceeds the limit."""
    user = await get_user(user_id)
    if not user:
        return

    for field in ("shadow_profile_user", "shadow_profile_partner"):
        text = user.get(field, "")
        if count_sentences(text) > SHADOW_PROFILE_MAX_SENTENCES:
            try:
                prompt = SHADOW_COMPRESS_PROMPT.format(
                    count=count_sentences(text), text=text
                )
                compressed = await generate(
                    system_prompt="Сожми текст до 5 ключевых предложений.",
                    user_message=prompt,
                    model_key="flash_lite",
                )
                await update_static_field(user_id, field, compressed.strip())
            except Exception as e:
                logger.error("Shadow compression error: %s", e)


async def summarize_and_close_session(
    user_id: str,
    window: list[dict[str, str]],
    dynamic: dict[str, Any],
) -> dict[str, Any] | None:
    """Section 10 — create session summary and close session."""
    if not window:
        await close_session(user_id)
        return None

    history = "\n".join(
        f"{m.get('role', '?')}: {m.get('text', '')}" for m in window
    )
    user_msg = (
        f"Динамический профиль:\n"
        f"Тип: {dynamic.get('situation_type', '?')}\n"
        f"Паттерн: {dynamic.get('dominant_pattern', '?')}\n"
        f"Фаза: {dynamic.get('current_phase', '?')}\n"
        f"Цель: {dynamic.get('user_goal', '?')}\n"
        f"Факты сессии: {dynamic.get('session_facts', [])}\n\n"
        f"История диалога:\n{history}"
    )

    try:
        result = await generate_json(
            system_prompt=SUMMARIZE_PROMPT,
            user_message=user_msg,
            model_key="flash_lite",
        )
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        summary = json.loads(cleaned)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Summarization error: %s", e)
        summary = {
            "situation_type": dynamic.get("situation_type", ""),
            "user_request": dynamic.get("current_request", ""),
            "dominant_pattern": dynamic.get("dominant_pattern", ""),
            "mood_in": None,
            "mood_out": None,
            "key_insight": "",
        }

    summary["session_id"] = dynamic.get("session_id", "")

    await add_session_summary(user_id, summary)

    mood_out = summary.get("mood_out")
    if mood_out is not None:
        user = await get_user(user_id)
        moods = user.get("mood_history", []) if user else []
        moods.append(mood_out)
        await update_static_field(user_id, "mood_history", moods)

    key_insight = summary.get("key_insight", "")
    if key_insight:
        await add_diary_entry(user_id, key_insight, source="auto")

    session_facts = dynamic.get("session_facts", [])
    for fact in session_facts:
        if fact and fact.strip():
            await add_important_fact(user_id, fact.strip())

    pending = dynamic.get("pending_task", "")
    if pending and pending != "-":
        await add_important_fact(user_id, f"Задание: {pending}")

    await _migrate_old_facts(user_id)

    pattern = dynamic.get("dominant_pattern", "")
    if pattern and pattern != "undefined":
        from db.operations import add_detected_pattern
        await add_detected_pattern(user_id, pattern)

    await _deduplicate_important_facts(user_id)

    await close_session(user_id)
    return summary


async def _migrate_old_facts(user_id: str):
    """One-time migration: convert string facts to structured format."""
    from db.models import _utcnow
    user = await get_user(user_id)
    if not user:
        return
    facts = user.get("important_facts", [])
    if not facts or all(isinstance(f, dict) for f in facts):
        return

    now = _utcnow().isoformat()
    migrated = []
    for f in facts:
        if isinstance(f, str):
            migrated.append({"text": f, "first_seen": now, "last_confirmed": now})
        else:
            migrated.append(f)

    await update_static_field(user_id, "important_facts", migrated)


async def _deduplicate_important_facts(user_id: str):
    """Remove duplicate/redundant important_facts using LLM, preserving timestamps."""
    user = await get_user(user_id)
    if not user:
        return
    facts = user.get("important_facts", [])
    if len(facts) <= 5:
        return

    fact_texts = []
    for f in facts:
        if isinstance(f, dict):
            fact_texts.append(f.get("text", ""))
        else:
            fact_texts.append(str(f))

    try:
        facts_text = "\n".join(f"- {t}" for t in fact_texts if t)
        result = await generate_json(
            system_prompt="Ты помощник по обработке данных. Отвечай строго JSON.",
            user_message=DEDUP_FACTS_PROMPT.format(facts=facts_text),
            model_key="flash_lite",
        )
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        deduped_texts = json.loads(cleaned)
        if not isinstance(deduped_texts, list) or not deduped_texts:
            return

        deduped_set = {t.strip().lower() for t in deduped_texts if isinstance(t, str)}

        # Rebuild with timestamps: keep the structured fact whose text survived dedup,
        # using the newest last_confirmed among merged duplicates
        text_to_meta: dict[str, dict] = {}
        for f in facts:
            if isinstance(f, dict):
                text = f.get("text", "").strip().lower()
                if text not in text_to_meta or f.get("last_confirmed", "") > text_to_meta[text].get("last_confirmed", ""):
                    text_to_meta[text] = f

        result_facts = []
        for dt in deduped_texts:
            if not isinstance(dt, str):
                continue
            key = dt.strip().lower()
            if key in text_to_meta:
                meta = text_to_meta[key]
                result_facts.append({"text": dt.strip(), "first_seen": meta.get("first_seen", ""), "last_confirmed": meta.get("last_confirmed", "")})
            else:
                from db.models import _utcnow
                now = _utcnow().isoformat()
                result_facts.append({"text": dt.strip(), "first_seen": now, "last_confirmed": now})

        if result_facts:
            await update_static_field(user_id, "important_facts", result_facts)
    except Exception as e:
        logger.error("Fact deduplication error: %s", e)
