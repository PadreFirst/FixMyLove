from __future__ import annotations
import logging
from typing import Any

from db.operations import update_user, update_static_field
from utils.constants import (
    AttachmentStyle,
    ATTACHMENT_QUESTIONS,
    ATTACHMENT_KEY,
)

logger = logging.getLogger(__name__)


class OnboardingState:
    """Tracks onboarding progress in-memory per user.

    Flow:
      privacy → welcome → name → age → relationship_status
      → (if dating) partner_name → partner_age → duration → note
      → (if broke_up) breakup_note
      → attachment_q1..q5 → diary_offer → (diary_schedule) → complete
    """

    STEPS_BASE = ["name", "age", "relationship_status"]
    STEPS_DATING = ["partner_name", "partner_age", "duration", "note"]
    STEPS_BROKE_UP = ["breakup_note"]
    STEPS_ATTACHMENT = ["att_q1", "att_q2", "att_q3", "att_q4", "att_q5"]
    STEPS_DIARY = ["diary_offer"]
    STEP_COMPLETE = "complete"

    def __init__(self):
        self._user_steps: dict[str, list[str]] = {}
        self._user_index: dict[str, int] = {}
        self._attachment_answers: dict[str, list[str]] = {}

    def start(self, user_id: str):
        self._user_steps[user_id] = list(self.STEPS_BASE)
        self._user_index[user_id] = 0
        self._attachment_answers[user_id] = []

    def current_step(self, user_id: str) -> str | None:
        steps = self._user_steps.get(user_id)
        idx = self._user_index.get(user_id, 0)
        if steps is None or idx >= len(steps):
            return None
        return steps[idx]

    def advance(self, user_id: str):
        self._user_index[user_id] = self._user_index.get(user_id, 0) + 1

    def insert_steps_after_current(self, user_id: str, new_steps: list[str]):
        steps = self._user_steps.get(user_id, [])
        idx = self._user_index.get(user_id, 0) + 1
        for i, s in enumerate(new_steps):
            steps.insert(idx + i, s)
        self._user_steps[user_id] = steps

    def add_attachment_answer(self, user_id: str, letter: str):
        self._attachment_answers.setdefault(user_id, []).append(letter)

    def compute_attachment_style(self, user_id: str) -> AttachmentStyle:
        answers = self._attachment_answers.get(user_id, [])
        if not answers:
            return AttachmentStyle.ANXIOUS

        counts: dict[str, int] = {}
        for a in answers:
            counts[a] = counts.get(a, 0) + 1

        max_count = max(counts.values())
        winners = [k for k, v in counts.items() if v == max_count]

        if len(winners) == 1:
            return ATTACHMENT_KEY.get(winners[0], AttachmentStyle.ANXIOUS)

        priority = ["Б", "Г", "В", "А"]
        for p in priority:
            if p in winners:
                return ATTACHMENT_KEY.get(p, AttachmentStyle.ANXIOUS)

        return AttachmentStyle.ANXIOUS

    def cleanup(self, user_id: str):
        self._user_steps.pop(user_id, None)
        self._user_index.pop(user_id, None)
        self._attachment_answers.pop(user_id, None)


onboarding_state = OnboardingState()


def get_step_message(step: str, user: dict[str, Any] | None = None, q_index: int = 0) -> str | None:
    """Return the message to send for a given onboarding step."""
    messages = {
        "name": "Как тебя зовут?",
        "age": "Сколько тебе лет?",
        "partner_name": "Как зовут твою половинку?",
        "partner_age": "А сколько ей/ему лет?",
        "duration": "Сколько лет вы вместе?",
        "note": "Расскажи в паре предложений о ваших отношениях — что сейчас беспокоит?",
        "breakup_note": "Как давно расстались? Хочешь разобраться в том что было — или думаешь о воссоединении?",
    }

    if step in messages:
        return messages[step]

    if step.startswith("att_q"):
        idx = int(step[-1]) - 1
        if 0 <= idx < len(ATTACHMENT_QUESTIONS):
            return ATTACHMENT_QUESTIONS[idx]["text"]

    if step == "diary_offer":
        return (
            "Последнее — после каждой сессии я записываю ключевые выводы в твой дневник. "
            "Ты тоже можешь добавлять записи в любой момент.\n\n"
            "Напоминать тебе вести дневник?"
        )

    return None


STEP_REPROMPTS = {
    "name": "Не уловил имя — напиши просто, как тебя зовут (например: Маша).",
    "age": "Нужен возраст числом от 10 до 120. Напиши цифрой, например: 28.",
    "relationship_status": (
        "Не понял статус. Напиши своими словами — например: «в отношениях», "
        "«расстались», «ищу», «всё сложно»."
    ),
    "partner_name": "Как зовут твоего партнёра? Достаточно имени.",
    "partner_age": "Возраст партнёра числом от 10 до 120. Например: 30.",
    "duration": "Напиши сколько лет вы вместе цифрой. Например: 3.",
    "note": "Напиши пару предложений о ваших отношениях — что сейчас беспокоит.",
    "breakup_note": "Расскажи коротко: как давно расстались и что сейчас важнее разобрать.",
    "diary_schedule": "Напиши расписание в свободной форме — например: «по вторникам в 19:00» или «каждый день утром».",
}


def get_step_reprompt(step: str) -> str:
    """Return a softer, reworded message asking the user to answer again."""
    if step in STEP_REPROMPTS:
        return STEP_REPROMPTS[step]
    if step.startswith("att_q"):
        return (
            "Нажми на один из вариантов — или опиши своими словами, как ты обычно реагируешь."
        )
    return "Попробуй ответить ещё раз, пожалуйста."


async def _classify_attachment_freeform(text: str) -> str | None:
    """Classify free-form user text into А/Б/В/Г attachment option via LLM."""
    from ai.gemini import generate
    prompt = (
        "Ты классифицируешь ответ пользователя на вопрос о привязанности.\n"
        "Варианты:\n"
        "А — надёжный стиль: открыт, спокойно разбирается\n"
        "Б — тревожный: переживает, хочет больше контакта, боится потерять\n"
        "В — избегающий: уходит в себя, нужно время, справляется сам\n"
        "Г — дезорганизованный: «по-разному», хаотично, противоречиво\n\n"
        "Верни ТОЛЬКО одну букву: А, Б, В или Г."
    )
    try:
        raw = await generate(
            system_prompt=prompt,
            user_message=text.strip()[:500],
            model_key="flash_lite",
        )
        letter = (raw or "").strip().upper()[:1]
        if letter in "АБВГ":
            return letter
        # tolerate latin answer
        mapping = {"A": "А", "B": "Б", "C": "В", "D": "Г"}
        return mapping.get(letter)
    except Exception:
        return None


async def _classify_relationship_freeform(text: str) -> str:
    """Normalize free-form relationship status answer."""
    lower = text.lower().strip()
    if any(w in lower for w in ("брак", "женат", "замужем")):
        return "брак"
    if "живём" in lower or "живем" in lower:
        return "живём вместе"
    if any(w in lower for w in ("в отношениях", "встречаемся", "вместе", "пара", "парень", "девушк", "муж", "жена")):
        return "встречаемся"
    if any(w in lower for w in ("расстал", "разошл", "бывш", "развод", "развел", "развёл")):
        return "расстались"
    if any(w in lower for w in ("ищу", "одинок", "свободен", "свободна", "один", "одна")):
        return "ищу"
    return "неопределённость"


async def process_onboarding_answer(
    user_id: str, step: str, text: str, user_doc: dict[str, Any]
) -> dict[str, Any]:
    """Process user's answer for an onboarding step.

    Returns dict with:
      - valid: True if answer accepted, False → caller should re-prompt
      - field_updates: dict of fields to update in DB
      - next_steps: list of steps to insert (e.g. dating path)
      - attachment_letter: if answering attachment question
    """
    result: dict[str, Any] = {
        "valid": False,
        "field_updates": {},
        "next_steps": [],
        "attachment_letter": None,
    }

    clean = (text or "").strip()

    if step == "name":
        if clean and 1 <= len(clean) <= 50:
            result["field_updates"]["name"] = clean
            result["valid"] = True

    elif step == "age":
        digits = "".join(c for c in clean if c.isdigit())[:3]
        if digits:
            try:
                age = int(digits)
                if 10 <= age <= 120:
                    result["field_updates"]["age"] = age
                    result["valid"] = True
            except ValueError:
                pass

    elif step == "relationship_status":
        if not clean:
            return result
        status = await _classify_relationship_freeform(clean)
        result["field_updates"]["relationship_status"] = status
        result["valid"] = True
        if status in ("встречаемся", "живём вместе", "брак"):
            result["next_steps"] = (
                OnboardingState.STEPS_DATING
                + OnboardingState.STEPS_ATTACHMENT
                + OnboardingState.STEPS_DIARY
            )
        elif status == "расстались":
            result["next_steps"] = (
                OnboardingState.STEPS_BROKE_UP
                + OnboardingState.STEPS_ATTACHMENT
                + OnboardingState.STEPS_DIARY
            )
        else:
            result["next_steps"] = (
                OnboardingState.STEPS_ATTACHMENT + OnboardingState.STEPS_DIARY
            )

    elif step == "partner_name":
        if clean and 1 <= len(clean) <= 50:
            result["field_updates"]["partner_name"] = clean
            result["valid"] = True

    elif step == "partner_age":
        digits = "".join(c for c in clean if c.isdigit())[:3]
        if digits:
            try:
                age = int(digits)
                if 10 <= age <= 120:
                    result["field_updates"]["partner_age"] = age
                    result["valid"] = True
            except ValueError:
                pass

    elif step == "duration":
        digits = "".join(c for c in clean if c.isdigit())[:3]
        if digits:
            try:
                num = int(digits)
                result["field_updates"]["relationship_duration"] = num
                result["valid"] = True
            except ValueError:
                pass

    elif step == "note":
        if len(clean) >= 3:
            result["field_updates"]["relationship_note"] = clean[:300]
            result["valid"] = True

    elif step == "breakup_note":
        if len(clean) >= 3:
            result["field_updates"]["relationship_note"] = clean[:300]
            result["valid"] = True

    elif step.startswith("att_q"):
        letter = clean.upper()
        chosen: str | None = None
        if letter and letter[0] in "АБВГ":
            chosen = letter[0]
        elif letter and letter[0] in "ABCD":
            chosen = {"A": "А", "B": "Б", "C": "В", "D": "Г"}.get(letter[0])
        else:
            # free-form text — classify via LLM
            if len(clean) >= 2:
                chosen = await _classify_attachment_freeform(clean)
        if chosen:
            result["attachment_letter"] = chosen
            result["valid"] = True

    elif step == "diary_offer":
        lower = clean.lower()
        if any(w in lower for w in ("да", "давай", "ок", "окей", "хорошо", "можно", "ага", "угу")):
            result["field_updates"]["diary_enabled"] = True
            result["next_steps"] = ["diary_schedule"]
            result["valid"] = True
        elif any(w in lower for w in ("нет", "не надо", "не нужно", "не хочу", "позже")):
            result["field_updates"]["diary_enabled"] = False
            result["valid"] = True

    elif step == "diary_schedule":
        if len(clean) >= 2:
            result["field_updates"]["diary_schedule"] = clean[:200]
            from services.schedule_parser import parse_schedule
            parsed = await parse_schedule(clean[:200])
            if parsed:
                result["field_updates"]["diary_schedule_parsed"] = parsed
            result["valid"] = True

    if result["valid"] and result["field_updates"]:
        await update_user(user_id, result["field_updates"])

    return result
