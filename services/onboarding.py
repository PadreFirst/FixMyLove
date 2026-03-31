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


async def process_onboarding_answer(
    user_id: str, step: str, text: str, user_doc: dict[str, Any]
) -> dict[str, Any]:
    """Process user's answer for an onboarding step.

    Returns dict with:
      - field_updates: dict of fields to update in DB
      - next_steps: list of steps to insert (e.g. dating path)
      - attachment_letter: if answering attachment question
    """
    result: dict[str, Any] = {"field_updates": {}, "next_steps": [], "attachment_letter": None}

    if step == "name":
        name = text.strip()
        if name and len(name) < 50:
            result["field_updates"]["name"] = name

    elif step == "age":
        try:
            age = int("".join(c for c in text if c.isdigit())[:3])
            if 10 <= age <= 120:
                result["field_updates"]["age"] = age
        except (ValueError, IndexError):
            pass

    elif step == "relationship_status":
        lower = text.lower().strip()
        if "да" in lower or "встречаемся" in lower or "вместе" in lower or "брак" in lower or "женат" in lower or "замужем" in lower:
            if "брак" in lower or "женат" in lower or "замужем" in lower:
                result["field_updates"]["relationship_status"] = "брак"
            elif "живём" in lower:
                result["field_updates"]["relationship_status"] = "живём вместе"
            else:
                result["field_updates"]["relationship_status"] = "встречаемся"
            result["next_steps"] = OnboardingState.STEPS_DATING + OnboardingState.STEPS_ATTACHMENT + OnboardingState.STEPS_DIARY
        elif "расстал" in lower or "нет" in lower:
            result["field_updates"]["relationship_status"] = "расстались"
            result["next_steps"] = OnboardingState.STEPS_BROKE_UP + OnboardingState.STEPS_ATTACHMENT + OnboardingState.STEPS_DIARY
        elif "ищу" in lower:
            result["field_updates"]["relationship_status"] = "ищу"
            result["next_steps"] = OnboardingState.STEPS_ATTACHMENT + OnboardingState.STEPS_DIARY
        else:
            result["field_updates"]["relationship_status"] = "неопределённость"
            result["next_steps"] = OnboardingState.STEPS_ATTACHMENT + OnboardingState.STEPS_DIARY

    elif step == "partner_name":
        name = text.strip()
        if name and len(name) < 50:
            result["field_updates"]["partner_name"] = name

    elif step == "partner_age":
        try:
            age = int("".join(c for c in text if c.isdigit())[:3])
            if 10 <= age <= 120:
                result["field_updates"]["partner_age"] = age
        except (ValueError, IndexError):
            pass

    elif step == "duration":
        try:
            num = int("".join(c for c in text if c.isdigit())[:3])
            result["field_updates"]["relationship_duration"] = num
        except (ValueError, IndexError):
            pass

    elif step == "note":
        if text.strip():
            result["field_updates"]["relationship_note"] = text.strip()[:300]

    elif step == "breakup_note":
        if text.strip():
            result["field_updates"]["relationship_note"] = text.strip()[:300]

    elif step.startswith("att_q"):
        letter = text.strip().upper()
        if letter and letter[0] in "АБВГ":
            cyrillic_to_letter = {"А": "А", "Б": "Б", "В": "В", "Г": "Г"}
            result["attachment_letter"] = cyrillic_to_letter.get(letter[0], letter[0])
        elif letter and letter[0] in "ABCD":
            mapping = {"A": "А", "B": "Б", "C": "В", "D": "Г"}
            result["attachment_letter"] = mapping.get(letter[0], "А")

    elif step == "diary_offer":
        lower = text.lower().strip()
        if "да" in lower:
            result["field_updates"]["diary_enabled"] = True
            result["next_steps"] = ["diary_schedule"]
        else:
            result["field_updates"]["diary_enabled"] = False

    elif step == "diary_schedule":
        if text.strip():
            result["field_updates"]["diary_schedule"] = text.strip()[:200]
            from services.schedule_parser import parse_schedule
            parsed = await parse_schedule(text.strip()[:200])
            if parsed:
                result["field_updates"]["diary_schedule_parsed"] = parsed

    if result["field_updates"]:
        await update_user(user_id, result["field_updates"])

    return result
