from __future__ import annotations
import re
from typing import Iterable


FRUSTRATION_MARKERS = [
    # direct complaints about the bot
    "не помогаешь",
    "не помогает",
    "бесполезно",
    "без толку",
    "одно и то же",
    "то же самое",
    "мы это уже обсуждали",
    "мы уже об этом говорили",
    "ты повторяешься",
    "опять ты",
    "опять одно",
    "надоел",
    "надоело",
    "хватит спрашивать",
    "не задавай",
    "снова вопрос",
    "снова вопросы",
    "тупо спрашиваешь",
    "ты меня не слышишь",
    "не слышишь меня",
    "я уже говорил",
    "я уже говорила",
    "я же сказал",
    "я же сказала",
    "ничего не понял",
    "ничего не поняла",
    "скучно",
    "вода",
    "общие слова",
    "клише",
    "банально",
    "как у робота",
]

REJECT_STRATEGY_MARKERS = [
    "это не работает",
    "не сработает",
    "уже пробовал",
    "уже пробовала",
    "это я делал",
    "это я делала",
    "это не поможет",
    "не про это",
    "это не то",
    "не отвечаешь на вопрос",
    "ты не понял",
    "ты не поняла",
]


def count_frustration_markers(text: str) -> int:
    """Count distinct frustration markers in a single message."""
    if not text:
        return 0
    lower = text.lower()
    count = 0
    for m in FRUSTRATION_MARKERS:
        if m in lower:
            count += 1
    for m in REJECT_STRATEGY_MARKERS:
        if m in lower:
            count += 1
    # CAPSLOCK rage (>= 6 uppercase letters in a row, excluding single words)
    if re.search(r"[А-ЯA-Z]{6,}", text):
        count += 1
    return count


def detect_frustration_in_window(window: Iterable[dict]) -> int:
    """Return how many recent user messages contain frustration markers.

    Window is the sliding_window list [{role, text, ts}, ...].
    Looks only at the last 4 user-role messages.
    """
    users = [m for m in window if m.get("role") == "user"]
    recent = users[-4:]
    hits = 0
    for m in recent:
        if count_frustration_markers(m.get("text", "")) > 0:
            hits += 1
    return hits


def average_user_message_length(window: Iterable[dict], last_n: int = 3) -> int:
    """Average char length of last N user messages. 0 if none."""
    users = [m for m in window if m.get("role") == "user"]
    recent = users[-last_n:]
    if not recent:
        return 0
    total = sum(len(m.get("text", "")) for m in recent)
    return total // len(recent)


def build_frustration_hint(frustration_hits: int) -> str:
    """Build a prompt-injection hint when the user seems frustrated."""
    if frustration_hits <= 0:
        return ""
    if frustration_hits == 1:
        return (
            "[СИГНАЛ ФРУСТРАЦИИ: пользователь намекает что подход не работает.]\n"
            "Признай это коротко (1 предложение), смени ракурс. Задай другой тип вопроса "
            "или предложи конкретный инструмент вместо уточнения."
        )
    # 2+ hits — severe
    return (
        "[!!! КРИТИЧНАЯ ФРУСТРАЦИЯ: пользователь уже несколько раз показал что подход не работает !!!]\n"
        "ОБЯЗАТЕЛЬНО сделай следующее в этом же ответе:\n"
        "1. Коротко признай — одним предложением, без оправданий: 'Слышу, захожу по-другому.'\n"
        "2. Сформулируй 2-3 пункта того что ты уже понял из разговора.\n"
        "3. Предложи 2-3 ПРИНЦИПИАЛЬНО разных следующих шага (коротко, по 1 строке):\n"
        "   например: конкретный эксперимент / разбор конкретной ситуации / проработка корней / пауза.\n"
        "4. Дай пользователю выбрать. НЕ задавай уточняющих вопросов про чувства.\n"
        "НИКАКИХ вариаций предыдущего подхода. Смени тактику радикально."
    )


def build_length_hint(avg_len: int) -> str:
    """Adaptive response length based on user's typical message size."""
    if avg_len <= 0:
        return ""
    if avg_len < 40:
        return (
            "[АДАПТАЦИЯ ДЛИНЫ: пользователь пишет очень коротко. "
            "Твой ответ — максимум 1-2 коротких предложения и один вопрос. "
            "НЕ засыпай текстом — это отпугнёт.]"
        )
    if avg_len < 120:
        return (
            "[АДАПТАЦИЯ ДЛИНЫ: пользователь пишет сдержанно. "
            "Твой ответ — 2-3 предложения максимум.]"
        )
    if avg_len < 300:
        return ""  # natural length is fine
    return (
        "[АДАПТАЦИЯ ДЛИНЫ: пользователь пишет развёрнуто — можно позволить "
        "3-5 предложений, но не больше. Никаких простыней.]"
    )
