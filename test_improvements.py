"""Unit tests for UX improvements — no network/DB required."""
from __future__ import annotations
import asyncio
import sys
import traceback
from unittest.mock import AsyncMock, patch


PASS = "\033[92mOK\033[0m"
FAIL = "\033[91mFAIL\033[0m"


results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    mark = PASS if ok else FAIL
    print(f"{mark}  {name}" + (f"  — {detail}" if detail else ""))


async def test_soften_capslock():
    from utils.text import soften_capslock

    cases = [
        ("НИКОГДА не повторяй", "никогда не повторяй"),
        ("ЭТО ПРОСТО ОРЁТ", "ЭТО просто орёт"),  # 3-letter "ЭТО" untouched
        ("Слово ОК не трогаем", "Слово ОК не трогаем"),  # 2 letters — untouched
        ("Обычный текст", "Обычный текст"),
        ("USA и РФ оставляем, но КРИЧАТЬ нельзя", "USA и РФ оставляем, но кричать нельзя"),
    ]
    for inp, expected in cases:
        got = soften_capslock(inp)
        assert got == expected, f"{inp!r} -> {got!r} (expected {expected!r})"


async def test_split_long_message():
    from utils.text import split_long_message

    short = "Короткий текст."
    assert split_long_message(short) == [short]

    long = ("Первый абзац с текстом. " * 30) + "\n\n" + ("Второй абзац. " * 30)
    chunks = split_long_message(long, max_len=400)
    assert len(chunks) >= 2, f"expected split, got {len(chunks)}"
    assert all(len(c) <= 550 for c in chunks), [len(c) for c in chunks]

    # No double-split, no empty
    assert all(c.strip() for c in chunks)


async def test_frustration_detection():
    from services.frustration import (
        count_frustration_markers,
        detect_frustration_in_window,
        build_frustration_hint,
        build_length_hint,
    )

    assert count_frustration_markers("мне кажется это бесполезно") >= 1
    assert count_frustration_markers("ТЫ НИЧЕГО НЕ ПОНИМАЕШЬ") >= 1  # capslock
    assert count_frustration_markers("всё ок") == 0

    window = [
        {"role": "user", "text": "привет"},
        {"role": "bot", "text": "..."},
        {"role": "user", "text": "надоело одно и то же"},
        {"role": "bot", "text": "..."},
        {"role": "user", "text": "ты повторяешься"},
    ]
    hits = detect_frustration_in_window(window)
    assert hits >= 2, hits

    hint1 = build_frustration_hint(1)
    hint2 = build_frustration_hint(2)
    assert "СИГНАЛ" in hint1
    assert "КРИТИЧНАЯ" in hint2 and "радикально" in hint2.lower()

    assert build_length_hint(0) == ""
    assert "очень коротко" in build_length_hint(20)
    assert "сдержанно" in build_length_hint(80)
    assert "развёрнуто" in build_length_hint(500)


async def test_onboarding_validation_name():
    from services.onboarding import process_onboarding_answer

    with patch("services.onboarding.update_user", new=AsyncMock()):
        r = await process_onboarding_answer("u1", "name", "", {})
        assert r["valid"] is False

        r = await process_onboarding_answer("u1", "name", "Маша", {})
        assert r["valid"] is True
        assert r["field_updates"]["name"] == "Маша"

        r = await process_onboarding_answer("u1", "name", "А" * 80, {})
        assert r["valid"] is False


async def test_onboarding_validation_age():
    from services.onboarding import process_onboarding_answer

    with patch("services.onboarding.update_user", new=AsyncMock()):
        r = await process_onboarding_answer("u1", "age", "abc", {})
        assert r["valid"] is False

        r = await process_onboarding_answer("u1", "age", "5", {})
        assert r["valid"] is False  # too young

        r = await process_onboarding_answer("u1", "age", "200", {})
        assert r["valid"] is False  # too old

        r = await process_onboarding_answer("u1", "age", "мне 28 лет", {})
        assert r["valid"] is True
        assert r["field_updates"]["age"] == 28


async def test_onboarding_relationship_freeform():
    from services.onboarding import process_onboarding_answer

    with patch("services.onboarding.update_user", new=AsyncMock()):
        r = await process_onboarding_answer("u1", "relationship_status", "в браке уже 5 лет", {})
        assert r["valid"] is True
        assert r["field_updates"]["relationship_status"] == "брак"
        assert "partner_name" in r["next_steps"]

        r = await process_onboarding_answer("u1", "relationship_status", "недавно развелись", {})
        assert r["valid"] is True
        assert r["field_updates"]["relationship_status"] == "расстались"
        assert "breakup_note" in r["next_steps"]

        r = await process_onboarding_answer("u1", "relationship_status", "всё очень странно", {})
        assert r["valid"] is True
        assert r["field_updates"]["relationship_status"] == "неопределённость"


async def test_onboarding_attachment_freeform():
    from services.onboarding import process_onboarding_answer

    with patch("services.onboarding.update_user", new=AsyncMock()), \
         patch("services.onboarding._classify_attachment_freeform", new=AsyncMock(return_value="Б")):
        r = await process_onboarding_answer("u1", "att_q1", "я всегда тревожусь и боюсь что бросят", {})
        assert r["valid"] is True
        assert r["attachment_letter"] == "Б"

    with patch("services.onboarding.update_user", new=AsyncMock()):
        r = await process_onboarding_answer("u1", "att_q1", "Б", {})
        assert r["valid"] is True
        assert r["attachment_letter"] == "Б"

        r = await process_onboarding_answer("u1", "att_q1", "B", {})  # latin
        assert r["valid"] is True
        assert r["attachment_letter"] == "Б"


async def test_onboarding_reprompt_message():
    from services.onboarding import get_step_reprompt

    assert "возраст" in get_step_reprompt("age").lower()
    assert "имя" in get_step_reprompt("name").lower()
    assert "расписан" in get_step_reprompt("diary_schedule").lower()
    assert "словами" in get_step_reprompt("att_q1").lower()


async def test_prompt_has_no_capslock_rule():
    # New prompt forbids CAPSLOCK
    from ai.prompts import SYSTEM_PROMPT_TEMPLATE
    assert "КАПСЛОКОМ" in SYSTEM_PROMPT_TEMPLATE or "капслок" in SYSTEM_PROMPT_TEMPLATE.lower()


async def test_prompt_builder_adaptive():
    """Build prompt with frustration in window — must contain the hint."""
    from ai.prompts import build_full_system_prompt

    user = {"name": "Тест", "age": 30}
    dynamic = {
        "session_open": True,
        "current_phase": "mapping",
        "dominant_pattern": "undefined",
        "sliding_window": [
            {"role": "user", "text": "надоело одно и то же"},
            {"role": "bot", "text": "..."},
            {"role": "user", "text": "ты повторяешься и это бесполезно"},
        ],
    }
    prompt = build_full_system_prompt(user, dynamic)
    assert "КРИТИЧНАЯ ФРУСТРАЦИЯ" in prompt or "СИГНАЛ ФРУСТРАЦИИ" in prompt

    # short user messages -> length hint
    dynamic2 = {
        "session_open": True,
        "current_phase": "mapping",
        "dominant_pattern": "undefined",
        "sliding_window": [
            {"role": "user", "text": "да"},
            {"role": "bot", "text": "..."},
            {"role": "user", "text": "ну ок"},
            {"role": "bot", "text": "..."},
            {"role": "user", "text": "угу"},
        ],
    }
    prompt2 = build_full_system_prompt(user, dynamic2)
    assert "очень коротко" in prompt2


async def test_reset_keyboard():
    from bot.keyboards import reset_confirm_keyboard, relationship_status_keyboard, attachment_question_keyboard
    kb = reset_confirm_keyboard()
    assert any(b.callback_data == "reset_confirm" for row in kb.inline_keyboard for b in row)
    assert any(b.callback_data == "reset_cancel" for row in kb.inline_keyboard for b in row)

    rel = relationship_status_keyboard()
    assert any(b.callback_data == "rel_other" for row in rel.inline_keyboard for b in row)

    att = attachment_question_keyboard(0)
    assert any(b.callback_data == "att_free_0" for row in att.inline_keyboard for b in row)


async def test_typing_keeper_cancels():
    """Ensure TypingKeeper background task stops on exit."""
    from utils.typing_keeper import TypingKeeper

    class FakeBot:
        def __init__(self):
            self.calls = 0
        async def send_chat_action(self, chat_id, action):
            self.calls += 1

    bot = FakeBot()
    async with TypingKeeper(bot, 123, interval=0.05):
        await asyncio.sleep(0.12)

    calls_after = bot.calls
    await asyncio.sleep(0.2)
    # Should not grow once context exited
    assert bot.calls == calls_after, f"{bot.calls} vs {calls_after}"
    assert calls_after >= 2


TESTS = [
    ("soften_capslock", test_soften_capslock),
    ("split_long_message", test_split_long_message),
    ("frustration_detection", test_frustration_detection),
    ("onboarding_name_validation", test_onboarding_validation_name),
    ("onboarding_age_validation", test_onboarding_validation_age),
    ("onboarding_relationship_freeform", test_onboarding_relationship_freeform),
    ("onboarding_attachment_freeform", test_onboarding_attachment_freeform),
    ("onboarding_reprompt_message", test_onboarding_reprompt_message),
    ("prompt_has_no_capslock_rule", test_prompt_has_no_capslock_rule),
    ("prompt_builder_adaptive", test_prompt_builder_adaptive),
    ("reset_keyboard", test_reset_keyboard),
    ("typing_keeper_cancels", test_typing_keeper_cancels),
]


async def main():
    print(f"\n=== Running {len(TESTS)} improvement tests ===\n")
    for name, fn in TESTS:
        try:
            await fn()
            record(name, True)
        except AssertionError as e:
            record(name, False, str(e) or "assertion")
        except Exception as e:
            traceback.print_exc()
            record(name, False, f"{type(e).__name__}: {e}")

    failed = [r for r in results if not r[1]]
    print(f"\n=== {len(results) - len(failed)}/{len(results)} passed ===")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
