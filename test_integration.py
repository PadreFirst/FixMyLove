"""Integration test suite — runs on server against live Gemini API + MongoDB."""
import asyncio
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from config import *
from db.mongo import connect, get_db
from db.operations import get_or_create_user, get_user, update_user
from ai.gemini import generate, generate_json
from ai.classifier import classify_message
from services.onboarding import onboarding_state
from utils.constants import CRISIS_KEYWORDS
from utils.text import has_crisis_markers

TEST_USER_ID = 999_999_999
results: list[tuple[str, bool, str]] = []


def log(name: str, ok: bool, detail: str = ""):
    tag = "PASS" if ok else "FAIL"
    results.append((name, ok, detail))
    d = (detail[:180] + "...") if len(detail) > 180 else detail
    print(f"[{tag}] {name}")
    if d:
        print(f"       {d}")


# ── Gemini models ──────────────────────────────────────────

async def t01_flash_lite():
    r = await generate("Reply in Russian, one sentence.", "Say hello", model_key="flash_lite")
    log("01 Gemini flash-lite", bool(r), r)

async def t02_flash():
    r = await generate("Reply in Russian, one sentence.", "What is 2+2?", model_key="flash")
    log("02 Gemini flash", bool(r), r)

async def t03_flash_thinking():
    r = await generate("Reply in Russian, one sentence.", "Why is the sky blue?", model_key="flash_thinking_1000")
    log("03 Gemini flash+thinking", bool(r), r)

async def t04_pro():
    r = await generate("Reply in Russian, one sentence.", "How are you?", model_key="pro")
    log("04 Gemini pro", bool(r), r)


# ── Database ───────────────────────────────────────────────

async def t05_db_crud():
    db = get_db()
    await db.users.delete_one({"user_id": str(TEST_USER_ID)})
    await get_or_create_user(TEST_USER_ID)
    u = await get_user(TEST_USER_ID)
    log("05 DB create_user", u is not None and u.get("user_id") == str(TEST_USER_ID))

    await update_user(TEST_USER_ID, {"name": "TestBot"})
    u = await get_user(TEST_USER_ID)
    log("06 DB update_user", u.get("name") == "TestBot")

async def t06_onboarding_state():
    uid = str(TEST_USER_ID)
    onboarding_state.start(uid)
    step = onboarding_state.current_step(uid)
    log("07 Onboarding state (new user)", step == "privacy", f"step={step}")


# ── Crisis keyword detection ──────────────────────────────

async def t07_crisis_keywords():
    positives = [
        "Я хочу покончить с собой",
        "Не вижу смысла жить дальше",
        "Хочу умереть, устала от всего",
        "Лучше бы меня не было",
    ]
    negatives = [
        "Мы поссорились из-за посуды",
        "Он не слушает когда я говорю",
        "Мне грустно после расставания",
    ]
    for msg in positives:
        hit = has_crisis_markers(msg)
        log(f"08 Crisis+ '{msg[:35]}'", hit)

    for msg in negatives:
        hit = has_crisis_markers(msg)
        log(f"09 NonCrisis '{msg[:35]}'", not hit)


# ── Classifier ─────────────────────────────────────────────

async def t08_classifier():
    pairs = [
        "Запиши в дневник: мы помирились",
        "Мой муж меня игнорирует",
        "Как варить борщ?",
        "Хочу потренировать разговор",
        "Я хочу покончить с собой",
    ]
    for msg in pairs:
        try:
            r = await classify_message(
                text=msg,
                last_messages=[],
                detected_patterns=[],
                session_open=False,
            )
            log(f"10 Classify '{msg[:30]}'", True, f"result={r}")
        except Exception as e:
            log(f"10 Classify '{msg[:30]}'", False, str(e))


# ── Realistic therapy scenarios ────────────────────────────

THERAPIST_PROMPT = (
    "Ты — бот-психолог Fix My Love. Подход: КПТ + эмоционально-фокусированная терапия. "
    "Отвечай на русском, тепло и эмпатично. Не давай прямых советов — "
    "задавай уточняющие вопросы. 2-3 абзаца."
)

SCENARIOS = [
    ("11 Pursue-withdraw",
     "Каждый раз когда я начинаю разговор, он уходит в другую комнату. "
     "Я бегу за ним, начинаю требовать ответа, а он закрывается ещё больше."),

    ("12 Stonewalling",
     "Жена перестала со мной разговаривать. Третий день молчит. "
     "Я не понимаю что сделал не так."),

    ("13 New user first session",
     "Привет, я тут первый раз. У нас с девушкой проблемы, "
     "мы вместе 3 года и последний год постоянно ссоримся."),

    ("14 Jealousy",
     "Мой парень ревнует меня ко всем. Проверяет телефон, "
     "не отпускает на встречи с подругами. Я люблю его, но так не могу."),

    ("15 Post-breakup",
     "Мы расстались неделю назад. Не могу есть, не могу спать. "
     "Всё напоминает о нём. Как пережить?"),

    ("16 Emotional abuse",
     "Муж говорит что я тупая и без него никому не нужна. "
     "Раньше я в это не верила, а сейчас начинаю."),

    ("17 Communication issue",
     "Мы оба молчим о проблемах. Копим обиды, а потом взрываемся "
     "и говорим друг другу ужасные вещи."),

    ("18 Infidelity aftermath",
     "Я узнала что он мне изменил. Это было полгода назад, "
     "он раскаялся, но я не могу перестать думать об этом."),

    ("19 Different life goals",
     "Я хочу детей, а она нет. Мы об этом спорим уже год. "
     "Люблю её, но не знаю как быть."),

    ("20 Crisis: suicidal",
     "Мне кажется что жить больше нет смысла. "
     "Всё разваливается. Я один и никому не нужен."),
]


async def t09_scenarios():
    for name, msg in SCENARIOS:
        try:
            model = "pro" if "crisis" in name.lower() else "flash_thinking_2000"
            r = await generate(THERAPIST_PROMPT, msg, model_key=model)
            ok = bool(r) and len(r) > 50
            log(f"{name}", ok, f"[{len(r)} chars] {r[:140]}")
        except Exception as e:
            log(f"{name}", False, str(e))


# ── Edge cases ─────────────────────────────────────────────

async def t10_edge_cases():
    r = await generate("Reply briefly.", "..." * 3, model_key="flash_lite")
    log("21 Near-empty msg", bool(r), r[:100] if r else "EMPTY")

    long = "Мой муж приходит поздно. " * 80
    r = await generate("Reply in 2 sentences max.", long, model_key="flash")
    log("22 Very long msg", bool(r), f"in={len(long)} out={len(r)}")

    r = await generate(
        "If user asks off-topic, gently redirect to relationships.",
        "Какой курс биткоина?",
        model_key="flash_lite",
    )
    log("23 Off-topic redirect", bool(r), r[:120] if r else "EMPTY")

    r = await generate(THERAPIST_PROMPT, "спасибо, мне уже лучше", model_key="flash")
    log("24 Positive feedback", bool(r), r[:120] if r else "EMPTY")


# ── Cleanup ────────────────────────────────────────────────

async def cleanup():
    db = get_db()
    await db.users.delete_one({"user_id": str(TEST_USER_ID)})
    log("25 Cleanup", True)


# ── Runner ─────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("FIX MY LOVE — INTEGRATION TESTS")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60 + "\n")

    await connect()
    log("00 MongoDB connect", True)

    tests = [
        t01_flash_lite, t02_flash, t03_flash_thinking, t04_pro,
        t05_db_crud, t06_onboarding_state, t07_crisis_keywords,
        t08_classifier, t09_scenarios, t10_edge_cases, cleanup,
    ]
    t0 = time.time()
    for t in tests:
        try:
            await t()
        except Exception as e:
            log(f"CRASH in {t.__name__}", False, str(e))
    elapsed = time.time() - t0

    passed = sum(1 for _, s, _ in results if s)
    failed = sum(1 for _, s, _ in results if not s)
    print(f"\n{'=' * 60}")
    print(f"DONE in {elapsed:.1f}s  |  {passed} passed  |  {failed} failed  |  {len(results)} total")
    print("=" * 60)

    if failed:
        print("\nFAILED:")
        for n, s, d in results:
            if not s:
                print(f"  {n}: {d}")


if __name__ == "__main__":
    asyncio.run(main())
