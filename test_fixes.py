"""Unit tests for fixes:
- Fix 1: voice during onboarding -> transcription goes to current step
- Fix 2: /start mid-onboarding does NOT reset progress
Run locally or on server: python3 test_fixes.py
Uses mocks for aiogram Bot/Message and Gemini transcription.
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))

from services.onboarding import onboarding_state

TEST_UID = "77777777"
results: list[tuple[str, bool, str]] = []


def log(name: str, ok: bool, detail: str = ""):
    tag = "PASS" if ok else "FAIL"
    results.append((name, ok, detail))
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))


def make_fake_message(text: str | None = None, voice=None):
    m = MagicMock()
    m.from_user.id = int(TEST_UID)
    m.chat.id = int(TEST_UID)
    m.text = text
    m.voice = voice
    m.caption = None
    m.answer = AsyncMock()
    m.bot = MagicMock()
    m.bot.send_chat_action = AsyncMock()
    m.bot.get_file = AsyncMock(return_value=MagicMock(file_path="voice.ogg"))
    m.bot.download_file = AsyncMock()
    m.model_copy = lambda update: make_fake_message(text=update.get("text"))
    return m


# ═══════════════════════════════════════════════════════════════
# FIX 1: /start does NOT reset onboarding in progress
# ═══════════════════════════════════════════════════════════════

async def test_start_does_not_reset_mid_onboarding():
    """If user is mid-onboarding, /start should resume, not restart."""
    from bot.handlers.start import cmd_start
    from db.operations import get_or_create_user

    onboarding_state.cleanup(TEST_UID)
    onboarding_state.start(TEST_UID)
    onboarding_state.advance(TEST_UID)
    onboarding_state.advance(TEST_UID)
    step_before = onboarding_state.current_step(TEST_UID)

    fake_msg = make_fake_message(text="/start")

    with patch("bot.handlers.start.get_or_create_user",
               new=AsyncMock(return_value={"onboarding_complete": False})):
        with patch("bot.handlers.start.update_static_field", new=AsyncMock()):
            await cmd_start(fake_msg)

    step_after = onboarding_state.current_step(TEST_UID)

    log(
        "FIX-1 /start preserves mid-onboarding step",
        step_before == step_after and step_before is not None,
        f"before={step_before} after={step_after}",
    )
    onboarding_state.cleanup(TEST_UID)


async def test_start_starts_fresh_for_new_user():
    """For a truly new user (no active step), /start should begin onboarding."""
    from bot.handlers.start import cmd_start

    onboarding_state.cleanup(TEST_UID)
    fake_msg = make_fake_message(text="/start")

    with patch("bot.handlers.start.get_or_create_user",
               new=AsyncMock(return_value={"onboarding_complete": False})):
        with patch("bot.handlers.start.update_static_field", new=AsyncMock()):
            await cmd_start(fake_msg)

    step_after = onboarding_state.current_step(TEST_UID)
    log(
        "FIX-1 /start starts fresh for new user",
        step_after == "name",
        f"step={step_after}",
    )
    onboarding_state.cleanup(TEST_UID)


async def test_start_does_nothing_if_onboarded():
    from bot.handlers.start import cmd_start

    onboarding_state.cleanup(TEST_UID)
    fake_msg = make_fake_message(text="/start")

    with patch("bot.handlers.start.get_or_create_user",
               new=AsyncMock(return_value={"onboarding_complete": True})):
        await cmd_start(fake_msg)

    fake_msg.answer.assert_awaited()
    args = fake_msg.answer.await_args
    sent = args[0][0] if args else ""
    log(
        "FIX-1 /start for returning user says welcome back",
        "возвращением" in sent.lower() or "вернулся" in sent.lower(),
        sent[:60],
    )


# ═══════════════════════════════════════════════════════════════
# FIX 2: Voice message during onboarding feeds into current step
# ═══════════════════════════════════════════════════════════════

async def test_voice_during_onboarding_feeds_step():
    """Voice during onboarding should be transcribed and routed to current step."""
    from bot.handlers.message import handle_voice

    onboarding_state.cleanup(TEST_UID)
    onboarding_state.start(TEST_UID)
    step = onboarding_state.current_step(TEST_UID)
    assert step == "name", f"expected start at 'name', got {step}"

    fake_voice = MagicMock(file_id="fid_123")
    fake_msg = make_fake_message(voice=fake_voice)

    consumed_flag = {"val": False}

    async def fake_handle_onboarding_text(msg):
        consumed_flag["val"] = True
        return True

    with patch("bot.handlers.message.get_or_create_user",
               new=AsyncMock(return_value={"onboarding_complete": False})):
        with patch("bot.handlers.message.transcribe_voice",
                   new=AsyncMock(return_value="Пётр")):
            with patch("bot.handlers.message.handle_onboarding_text",
                       new=fake_handle_onboarding_text):
                await handle_voice(fake_msg, fake_msg.bot)

    log(
        "FIX-2 voice during onboarding routed to onboarding",
        consumed_flag["val"],
        "handle_onboarding_text was called with transcript",
    )
    onboarding_state.cleanup(TEST_UID)


async def test_voice_transcription_failure_during_onboarding():
    """If transcription fails during onboarding, user gets an error, no crash."""
    from bot.handlers.message import handle_voice

    onboarding_state.cleanup(TEST_UID)
    onboarding_state.start(TEST_UID)

    fake_voice = MagicMock(file_id="fid_123")
    fake_msg = make_fake_message(voice=fake_voice)

    with patch("bot.handlers.message.get_or_create_user",
               new=AsyncMock(return_value={"onboarding_complete": False})):
        with patch("bot.handlers.message.transcribe_voice",
                   new=AsyncMock(return_value="")):
            await handle_voice(fake_msg, fake_msg.bot)

    sent_any = fake_msg.answer.await_args is not None
    log(
        "FIX-2 empty transcription handled gracefully",
        sent_any,
        "user got an error message, no crash",
    )
    onboarding_state.cleanup(TEST_UID)


async def test_voice_after_onboarding_goes_to_pipeline():
    """After onboarding, voice should reach process_message with tag prefix."""
    from bot.handlers.message import handle_voice

    fake_voice = MagicMock(file_id="fid_123")
    fake_msg = make_fake_message(voice=fake_voice)

    captured = {"text": None}

    async def fake_process_message(uid, text):
        captured["text"] = text
        return "ответ бота"

    with patch("bot.handlers.message.get_or_create_user",
               new=AsyncMock(return_value={"onboarding_complete": True})):
        with patch("bot.handlers.message.transcribe_voice",
                   new=AsyncMock(return_value="Жена молчит уже три дня")):
            with patch("bot.handlers.message.process_message",
                       new=fake_process_message):
                await handle_voice(fake_msg, fake_msg.bot)

    has_tag = captured["text"] and captured["text"].startswith("[голосовое сообщение]")
    log(
        "FIX-2 voice after onboarding reaches pipeline with tag",
        bool(has_tag),
        captured["text"] or "(nothing captured)",
    )


# ═══════════════════════════════════════════════════════════════
# Corner cases: onboarding answers
# ═══════════════════════════════════════════════════════════════

async def test_onboarding_invalid_age():
    """Non-numeric age answer should not crash and should not advance with bad data."""
    from services.onboarding import process_onboarding_answer

    result = await process_onboarding_answer(
        TEST_UID, "age", "блабла", {"user_id": TEST_UID}
    )
    log(
        "CORNER age=non-numeric returns no update",
        "age" not in result.get("field_updates", {}),
        str(result),
    )


async def test_onboarding_empty_name():
    from services.onboarding import process_onboarding_answer

    result = await process_onboarding_answer(
        TEST_UID, "name", "   ", {"user_id": TEST_UID}
    )
    log(
        "CORNER name=empty returns no update",
        "name" not in result.get("field_updates", {}),
        str(result),
    )


async def test_onboarding_very_long_note():
    from services.onboarding import process_onboarding_answer

    long_note = "А" * 2000
    result = await process_onboarding_answer(
        TEST_UID, "note", long_note, {"user_id": TEST_UID}
    )
    stored = result.get("field_updates", {}).get("relationship_note", "")
    log(
        "CORNER long note truncated to 300 chars",
        len(stored) <= 300 and len(stored) > 0,
        f"len={len(stored)}",
    )


async def test_onboarding_age_out_of_range():
    from services.onboarding import process_onboarding_answer

    for bad_age in ["5", "200", "999"]:
        result = await process_onboarding_answer(
            TEST_UID, "age", bad_age, {"user_id": TEST_UID}
        )
        log(
            f"CORNER age={bad_age} rejected",
            "age" not in result.get("field_updates", {}),
            str(result.get("field_updates", {})),
        )


async def test_onboarding_latin_attachment_letters():
    """Attachment question accepts both Latin ABCD and Cyrillic АБВГ."""
    from services.onboarding import process_onboarding_answer

    for ltr, expected in [("A", "А"), ("B", "Б"), ("C", "В"), ("D", "Г"),
                          ("А", "А"), ("Б", "Б")]:
        result = await process_onboarding_answer(
            TEST_UID, "att_q1", ltr, {"user_id": TEST_UID}
        )
        got = result.get("attachment_letter")
        log(
            f"CORNER attachment letter '{ltr}' -> '{expected}'",
            got == expected,
            f"got={got}",
        )


# ═══════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════

async def main():
    from db.mongo import connect
    await connect()

    tests = [
        test_start_does_not_reset_mid_onboarding,
        test_start_starts_fresh_for_new_user,
        test_start_does_nothing_if_onboarded,
        test_voice_during_onboarding_feeds_step,
        test_voice_transcription_failure_during_onboarding,
        test_voice_after_onboarding_goes_to_pipeline,
        test_onboarding_invalid_age,
        test_onboarding_empty_name,
        test_onboarding_very_long_note,
        test_onboarding_age_out_of_range,
        test_onboarding_latin_attachment_letters,
    ]
    for t in tests:
        try:
            await t()
        except Exception as e:
            log(f"CRASH in {t.__name__}", False, f"{type(e).__name__}: {e}")

    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{'=' * 60}")
    print(f"{passed} passed | {failed} failed | {len(results)} total")
    print("=" * 60)
    if failed:
        print("\nFAILED:")
        for n, ok, d in results:
            if not ok:
                print(f"  {n}: {d}")


if __name__ == "__main__":
    asyncio.run(main())
