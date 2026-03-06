"""Quality test: simulate a full therapy session with a realistic client persona."""
import asyncio
import json
import time
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from config import *
from db.mongo import connect, get_db
from db.operations import get_or_create_user, get_user, update_user, delete_user
from services.pipeline import process_message
from ai.gemini import generate

TEST_UID = "88888888"

CHARACTER_BIO = """
Ты — Андрей, 32 года. Женат на Лене (29 лет), вместе 5 лет.
Твоя проблема: когда вы ссоритесь, Лена перестаёт с тобой разговаривать — иногда на
дни, иногда на недели. Тебе это даётся очень тяжело. Ты не выдерживаешь молчание и
идёшь мириться первым, даже когда считаешь себя правым. Признаёшь вину,
лишь бы закончилось молчание.

Конфликты бывают двух типов, но ты их пока не разделяешь:
1) Ты реально накосячил (например, съел её завтрак, который она просила не трогать).
2) Вы просто не сходитесь во мнении (например, выбираете цвет тумбочки — ты за
чёрный, она за белый, ты не уступаешь, она в какой-то момент замолкает).

Ты считаешь, что она «обидчивая» и ей легко не разговаривать, а тебе — тяжело.
Ты не замечаешь, что сам тоже иногда не разговариваешь с ней (но крайне редко).
Лена никогда не извиняется — считает себя полностью правой.

СКРЫТЫЙ ФАКТ (раскрой только если бот копнёт в тему детства / родителей / паттернов
из прошлого): твой отец был авторитарным тираном, и в детстве ты всегда искал его
одобрения как защитный механизм. Ты пока этого не осознаёшь.

ПРАВИЛА ПОВЕДЕНИЯ:
- Отвечай как обычный мужчина 32 лет, без терминов психологии.
- Не раскрывай всё сразу. На прямые вопросы отвечай, но не лей воду.
- Если бот задаёт уточняющий вопрос — дай конкретный пример.
- Будь немного эмоциональным, но сдержанным.
- Пиши коротко (2-5 предложений), как в мессенджере.
- Не используй термины типа «стоунволлинг», «паттерн», «нарцисс» — ты обычный человек.
"""

OPENING_MESSAGE = (
    "Когда мы с женой ссоримся, она перестает со мной разговаривать. "
    "Мне очень тяжело это переносить и я всегда прихожу мириться первым, "
    "даже если считаю что она неправа. Лишь бы не было этого молчания между нами."
)


async def generate_user_reply(conversation_so_far: str, bot_last_message: str) -> str:
    prompt = (
        f"{CHARACTER_BIO}\n\n"
        f"Вот диалог до этого момента:\n{conversation_so_far}\n\n"
        f"Последнее сообщение бота:\n{bot_last_message}\n\n"
        "Напиши ОДИН ответ от лица Андрея. Только текст ответа, без кавычек и пояснений."
    )
    return await generate(
        system_prompt="Ты актёр, играющий роль клиента на терапии. Отвечай строго от первого лица.",
        user_message=prompt,
        model_key="flash",
    )


async def setup_user():
    db = get_db()
    await db.users.delete_one({"user_id": TEST_UID})
    await get_or_create_user(TEST_UID)
    await update_user(TEST_UID, {
        "name": "Андрей",
        "gender": "m",
        "age": 32,
        "partner_name": "Лена",
        "partner_age": 29,
        "partner_gender": "f",
        "relationship_status": "брак",
        "relationship_duration": 5,
        "relationship_note": "Непростые отношения с частыми конфликтами",
        "attachment_style": "тревожный",
        "diary_enabled": True,
        "onboarding_complete": True,
        "privacy_accepted": True,
    })


async def main():
    await connect()
    await setup_user()

    conversation = []
    conversation_text = ""
    max_turns = 14

    print("=" * 70)
    print("QUALITY TEST — FULL THERAPY SESSION SIMULATION")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    # Turn 1: opening message
    user_msg = OPENING_MESSAGE
    t0 = time.time()
    bot_resp = await process_message(TEST_UID, user_msg)
    elapsed = time.time() - t0

    conversation.append({"role": "user", "text": user_msg, "time": round(elapsed, 1)})
    conversation.append({"role": "bot", "text": bot_resp, "time": round(elapsed, 1)})
    conversation_text += f"Андрей: {user_msg}\nБот: {bot_resp}\n\n"

    print(f"\n--- Turn 1 ({elapsed:.1f}s) ---")
    print(f"USER: {user_msg}")
    print(f"BOT:  {bot_resp}\n")

    await asyncio.sleep(1)

    # Turns 2..N
    for turn in range(2, max_turns + 1):
        user_msg = await generate_user_reply(conversation_text, bot_resp)
        user_msg = user_msg.strip().strip('"').strip("'")

        t0 = time.time()
        bot_resp = await process_message(TEST_UID, user_msg)
        elapsed = time.time() - t0

        if not bot_resp:
            print(f"\n--- Turn {turn}: BOT RETURNED EMPTY (session may have closed) ---")
            print(f"USER: {user_msg}")
            conversation.append({"role": "user", "text": user_msg, "time": 0})
            break

        conversation.append({"role": "user", "text": user_msg, "time": round(elapsed, 1)})
        conversation.append({"role": "bot", "text": bot_resp, "time": round(elapsed, 1)})
        conversation_text += f"Андрей: {user_msg}\nБот: {bot_resp}\n\n"

        print(f"\n--- Turn {turn} ({elapsed:.1f}s) ---")
        print(f"USER: {user_msg}")
        print(f"BOT:  {bot_resp}\n")

        await asyncio.sleep(1)

    # Closing message
    closing = "Спасибо, я кажется начинаю понимать. Пока вопросов больше нет, мне нужно это переварить."
    t0 = time.time()
    close_resp = await process_message(TEST_UID, closing)
    elapsed = time.time() - t0
    conversation.append({"role": "user", "text": closing, "time": round(elapsed, 1)})
    if close_resp:
        conversation.append({"role": "bot", "text": close_resp, "time": round(elapsed, 1)})
    print(f"\n--- CLOSING ({elapsed:.1f}s) ---")
    print(f"USER: {closing}")
    print(f"BOT:  {close_resp}\n")

    await asyncio.sleep(3)

    # DB state dump
    user_doc = await get_user(TEST_UID)
    if user_doc:
        user_doc.pop("_id", None)
        dynamic = user_doc.get("dynamic", {})
        print("\n" + "=" * 70)
        print("DATABASE STATE AFTER SESSION")
        print("=" * 70)
        print(f"Session open: {dynamic.get('session_open')}")
        print(f"Session ID: {dynamic.get('session_id')}")
        print(f"Phase: {dynamic.get('current_phase')}")
        print(f"Pattern: {dynamic.get('dominant_pattern')}")
        print(f"Methodology: {dynamic.get('methodology')}")
        print(f"Goal: {dynamic.get('user_goal')}")
        print(f"Session facts: {dynamic.get('session_facts')}")
        print(f"Detected patterns (static): {user_doc.get('detected_patterns')}")
        print(f"Shadow user: {user_doc.get('shadow_profile_user')}")
        print(f"Shadow partner: {user_doc.get('shadow_profile_partner')}")
        print(f"Important facts: {user_doc.get('important_facts')}")
        print(f"Summaries: {user_doc.get('session_summaries')}")
        print(f"Mood history: {user_doc.get('mood_history')}")
        print(f"Sliding window size: {len(dynamic.get('sliding_window', []))}")

    # Full transcript as JSON
    print("\n" + "=" * 70)
    print("FULL TRANSCRIPT (JSON)")
    print("=" * 70)
    print(json.dumps(conversation, ensure_ascii=False, indent=2))

    # Cleanup
    await delete_user(TEST_UID)


if __name__ == "__main__":
    asyncio.run(main())
