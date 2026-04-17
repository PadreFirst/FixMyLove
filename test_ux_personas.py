"""UX simulation test: run long sessions with diverse, realistic personas.
Records full transcripts for qualitative analysis.

Persona types:
- frustrated: fed up, curses, skeptical
- unstructured: jumps between topics, short replies
- psychoeducated: knows terms, tests the bot
- minimal: very short answers, disengaged
- topic_jumper: starts with one problem, drifts to another
"""
import asyncio
import json
import time
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from config import *
from db.mongo import connect, get_db
from db.operations import get_or_create_user, update_user, delete_user, get_user
from services.pipeline import process_message
from ai.gemini import generate


PERSONAS = {
    "frustrated": {
        "uid": "66600001",
        "profile": {
            "name": "Дима", "age": 34, "gender": "m",
            "partner_name": "Оля", "partner_age": 30, "partner_gender": "f",
            "relationship_status": "брак", "relationship_duration": 8,
            "relationship_note": "Постоянные ссоры, усталость",
            "attachment_style": "избегающий",
        },
        "bio": """Ты — Дима, 34. Женат 8 лет, 2 детей. Устал от ссор и от психологии вообще.
Уже ходил к двум психологам — один советовал "говорить о чувствах", другой — "устанавливать границы". Не помогло.
Ты пришёл сюда с мыслью "ну посмотрим что этот ИИ может". К боту относишься скептически.
Если бот повторяется, задаёт много вопросов, говорит клише — ты это сразу замечаешь и пишешь прямо:
"опять ты про то же", "ты ничего нового не сказал", "это я и так знаю".
Отвечаешь коротко, иногда с матом, иногда резко. Не льёшь воду.
ПРАВИЛА: пиши 1-3 предложения. Матерись умеренно (1 раз в 3-4 реплики). Будь живым, не актёр.""",
        "opening": "Короче, я тут пробую. Жена опять устроила скандал из-за ерунды. Смысл я не понимаю какой-то.",
    },

    "minimal": {
        "uid": "66600002",
        "profile": {
            "name": "Саша", "age": 22, "gender": "f",
            "partner_name": "Никита", "partner_age": 24, "partner_gender": "m",
            "relationship_status": "встречаемся", "relationship_duration": 2,
            "relationship_note": "Вопросы по будущему",
            "attachment_style": "тревожный",
        },
        "bio": """Ты — Саша, 22. Встречаетесь 2 года с Никитой. Тебе тяжело писать длинные тексты.
Ты отвечаешь очень коротко: "да", "нет", "ну хз", "наверное", "не знаю". Иногда смайликом.
Ты не то чтобы не хочешь — просто не знаешь как формулировать. И ещё стесняешься.
Если бот задаёт слишком сложный вопрос — ты пишешь "хз" или "ну наверное".
Постепенно, через 5-6 сообщений, можешь начать раскрываться чуть больше (2-3 предложения).
ПРАВИЛА: отвечай 1-7 слов первые 4-5 реплик. Потом можешь раскрыться. Используй "((", "(((", "нуу".""",
        "opening": "привет. у меня с парнем странно все",
    },

    "psychoeducated": {
        "uid": "66600003",
        "profile": {
            "name": "Катя", "age": 29, "gender": "f",
            "partner_name": "Марк", "partner_age": 31, "partner_gender": "m",
            "relationship_status": "живём вместе", "relationship_duration": 4,
            "relationship_note": "Избегающий партнёр, работаю с терапевтом 2 года",
            "attachment_style": "тревожный",
        },
        "bio": """Ты — Катя, 29. Ты 2 года в личной терапии, читала книги Боулби, Готтмана, Перел.
Говоришь терминами: "дисрегуляция", "стоунволлинг", "газлайтинг", "тип привязанности".
У Марка избегающий тип привязанности (ты уже диагностировала), у тебя тревожный.
Ты хочешь от бота глубокого разбора, не базы. Если бот объясняет тебе что такое стоунволлинг — ты пишешь
"я это знаю, давай глубже". Ты можешь проверять бота: задать вопрос и оценить ответ.
Если бот говорит что-то упрощённое — ты укажешь: "это поверхностно".
ПРАВИЛА: пиши 3-5 предложений. Используй термины. Будь требовательной клиенткой.""",
        "opening": "Когда мы ссоримся, Марк уходит в стоунволлинг на 2-3 дня. У меня тревожный тип, у него избегающий. Я понимаю динамику, но не могу выйти из цикла pursue-withdraw.",
    },

    "topic_jumper": {
        "uid": "66600004",
        "profile": {
            "name": "Лена", "age": 31, "gender": "f",
            "partner_name": "Егор", "partner_age": 33, "partner_gender": "m",
            "relationship_status": "брак", "relationship_duration": 6,
            "relationship_note": "Много разных проблем",
            "attachment_style": "дезорганизованный",
        },
        "bio": """Ты — Лена, 31. Пришла с одной проблемой, но в голове у тебя ворох всего:
- Свекровь лезет в воспитание сына
- Муж мало помогает с ребёнком
- Ты устала от работы
- Думаешь ли идти к маме на выходные
- У подруги развод — страшно что с тобой так же
Ты начинаешь с одного, но через 2-3 реплики уходишь в другое. Иногда возвращаешься, иногда нет.
Если бот возвращает тебя к исходной теме — ты соглашаешься, но потом опять уходишь.
ПРАВИЛА: пиши 2-4 предложения. Каждые 2-3 реплики добавляй новую тему. Будь хаотичной, но живой.""",
        "opening": "Муж вчера опять сказал что я ворчу. А я не ворчу, я просто прошу помочь с ребёнком. Но он так сказал и ушёл в комнату.",
    },

    "resistant": {
        "uid": "66600005",
        "profile": {
            "name": "Артём", "age": 38, "gender": "m",
            "partner_name": "Ира", "partner_age": 36, "partner_gender": "f",
            "relationship_status": "брак", "relationship_duration": 12,
            "relationship_note": "Жена настояла на терапии",
            "attachment_style": "избегающий",
        },
        "bio": """Ты — Артём, 38. Женат 12 лет. Ты здесь, потому что жена пригрозила разводом если не начнёшь "заниматься отношениями".
Ты не видишь проблемы. Считаешь, что всё норм, это у жены "какие-то выдумки" после 30.
Ты не материшься, но холоден, сдержан. Можешь сказать "не знаю", "мне кажется нормально", "ну и что?".
На вопросы про чувства отвечаешь "ну нормально", "да обычно". Не раскрываешься легко.
Если бот даёт ценную мысль — ты подмечаешь про себя, но на словах: "может быть".
Через 7-8 реплик можешь дрогнуть и начать чуть больше говорить, если бот терпелив и не давит.
ПРАВИЛА: сухо, сдержанно, 1-3 предложения. Без эмоций. Редкое "хм" допустимо.""",
        "opening": "Жена сказала что мне надо с кем-то поговорить. Типа про отношения. Ну вот, говорю.",
    },
}


async def setup_user(uid: str, profile: dict):
    db = get_db()
    await db.users.delete_one({"user_id": uid})
    await get_or_create_user(uid)
    await update_user(uid, {
        **profile,
        "diary_enabled": False,
        "onboarding_complete": True,
        "privacy_accepted": True,
    })


async def gen_user_reply(bio: str, history_text: str, bot_last: str) -> str:
    prompt = (
        f"{bio}\n\n"
        f"Диалог до сих пор:\n{history_text}\n\n"
        f"Последнее сообщение бота:\n{bot_last}\n\n"
        "Напиши ОДИН ответ от лица персонажа. Только текст, без кавычек и пояснений, без указания имени."
    )
    return await generate(
        system_prompt="Ты актёр, играющий клиента. Строго в роли, от первого лица.",
        user_message=prompt,
        model_key="flash",
    )


async def run_persona(name: str, persona: dict, turns: int = 18):
    print(f"\n{'='*70}\nPERSONA: {name}\n{'='*70}")
    await setup_user(persona["uid"], persona["profile"])
    conversation = []
    hist = ""
    user_msg = persona["opening"]

    for turn in range(1, turns + 1):
        t0 = time.time()
        try:
            bot_resp = await process_message(persona["uid"], user_msg)
        except Exception as e:
            print(f"  [ERROR turn {turn}] {e}")
            break
        elapsed = time.time() - t0

        conversation.append({"turn": turn, "role": "user", "text": user_msg})
        conversation.append({"turn": turn, "role": "bot", "text": bot_resp, "time": round(elapsed, 1), "len": len(bot_resp or "")})
        hist += f"Клиент: {user_msg}\nБот: {bot_resp}\n\n"

        print(f"\n--- Turn {turn} ({elapsed:.1f}s, {len(bot_resp or '')} chars) ---")
        print(f"USER: {user_msg}")
        print(f"BOT:  {(bot_resp or '(empty)')[:300]}{'...' if len(bot_resp or '') > 300 else ''}")

        if not bot_resp:
            break

        if turn >= turns:
            break

        try:
            user_msg = await gen_user_reply(persona["bio"], hist, bot_resp)
            user_msg = user_msg.strip().strip('"').strip("'")
        except Exception as e:
            print(f"  [ERROR user_gen turn {turn}] {e}")
            break

        await asyncio.sleep(0.5)

    # Dump DB state
    udoc = await get_user(persona["uid"])
    dyn = (udoc or {}).get("dynamic", {}) if udoc else {}
    state = {
        "phase": dyn.get("current_phase"),
        "pattern": dyn.get("dominant_pattern"),
        "session_open": dyn.get("session_open"),
        "session_msgs": dyn.get("session_message_count"),
        "off_topic_count": dyn.get("off_topic_count"),
        "detected_patterns": (udoc or {}).get("detected_patterns"),
        "shadow_user": (udoc or {}).get("shadow_profile_user", "")[:200],
        "shadow_partner": (udoc or {}).get("shadow_profile_partner", "")[:200],
        "summaries_count": len((udoc or {}).get("session_summaries", [])),
    }
    print(f"\n[{name}] FINAL STATE: {json.dumps(state, ensure_ascii=False)}")

    await delete_user(persona["uid"])
    return {"persona": name, "turns": len([c for c in conversation if c['role']=='user']), "conversation": conversation, "state": state}


async def main():
    await connect()

    selected = ["frustrated", "minimal", "psychoeducated", "topic_jumper", "resistant"]
    all_results = []

    for name in selected:
        persona = PERSONAS[name]
        result = await run_persona(name, persona, turns=18)
        all_results.append(result)

    # Save full transcripts
    out_path = "/tmp/ux_simulation_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n\nSaved: {out_path}")
    print(f"Personas run: {len(all_results)}")


if __name__ == "__main__":
    asyncio.run(main())
