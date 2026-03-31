from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from ai.gemini import generate
from ai.prompts import PARSE_SCHEDULE_PROMPT

logger = logging.getLogger(__name__)

_VALID_MODES = {"daily", "weekdays", "weekends", "specific_days", "even_days", "odd_days", "monthly"}


async def parse_schedule(raw_text: str) -> dict[str, Any] | None:
    """Parse natural-language schedule into structured dict via Gemini.

    Returns None if parsing fails or input is empty.
    """
    text = raw_text.strip()
    if not text:
        return None

    local = _try_local_parse(text)
    if local is not None:
        return local

    try:
        result = await generate(
            system_prompt=PARSE_SCHEDULE_PROMPT,
            user_message=text,
            model_key="flash_lite",
        )
        result = result.strip()
        result = re.sub(r"^```(?:json)?\s*", "", result)
        result = re.sub(r"\s*```$", "", result)
        parsed = json.loads(result)
        return _validate_schedule(parsed)
    except Exception as e:
        logger.error("Schedule parse error for '%s': %s", text, e)
        return None


def _try_local_parse(text: str) -> dict[str, Any] | None:
    """Fast regex-based parse for simple unambiguous formats like '19:00' or 'в 19'."""
    s = text.lower().strip()

    hour: int | None = None
    minute: int = 0

    time_match = re.search(r"(\d{1,2})[:\.](\d{2})", s)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
    else:
        bare = re.fullmatch(r"(?:в\s+)?(\d{1,2})", s)
        if bare:
            hour = int(bare.group(1))

    if hour is not None and 0 <= hour <= 23 and 0 <= minute <= 59:
        has_day_keywords = any(kw in s for kw in (
            "понедельник", "вторник", "сред", "четверг", "пятниц", "суббот", "воскресен",
            "будн", "выходн", "ежедневн", "каждый день", "чётн", "нечётн", "месяц",
            "неделю", "недел",
        ))
        if not has_day_keywords:
            return {"hour": hour, "minute": minute, "mode": "daily", "days_of_week": [], "day_of_month": None}

    return None


def _validate_schedule(data: dict[str, Any]) -> dict[str, Any] | None:
    """Validate and normalise a parsed schedule dict."""
    try:
        hour = int(data.get("hour", -1))
        minute = int(data.get("minute", 0))
        mode = str(data.get("mode", "daily"))
        days_of_week = data.get("days_of_week") or []
        day_of_month = data.get("day_of_month")

        if not (0 <= hour <= 23):
            return None
        if not (0 <= minute <= 59):
            minute = 0
        if mode not in _VALID_MODES:
            mode = "daily"

        days_of_week = [int(d) for d in days_of_week if 0 <= int(d) <= 6]

        if mode == "specific_days" and not days_of_week:
            mode = "daily"

        if mode == "monthly":
            if day_of_month is not None:
                day_of_month = int(day_of_month)
                if not (1 <= day_of_month <= 31):
                    day_of_month = 1
            else:
                day_of_month = 1

        return {
            "hour": hour,
            "minute": minute,
            "mode": mode,
            "days_of_week": sorted(set(days_of_week)),
            "day_of_month": day_of_month if mode == "monthly" else None,
        }
    except (ValueError, TypeError) as e:
        logger.error("Schedule validation error: %s — data=%s", e, data)
        return None


def should_send_now(schedule: dict[str, Any], now_msk: datetime, tolerance_minutes: int = 2) -> bool:
    """Check whether *now_msk* falls within the delivery window of *schedule*."""
    hour = schedule.get("hour")
    minute = schedule.get("minute", 0)
    mode = schedule.get("mode", "daily")

    if hour is None:
        return False

    target_total = hour * 60 + minute
    current_total = now_msk.hour * 60 + now_msk.minute
    if abs(current_total - target_total) > tolerance_minutes:
        return False

    if mode == "daily":
        return True
    if mode == "weekdays":
        return now_msk.weekday() < 5
    if mode == "weekends":
        return now_msk.weekday() >= 5
    if mode == "specific_days":
        return now_msk.weekday() in schedule.get("days_of_week", [])
    if mode == "even_days":
        return now_msk.day % 2 == 0
    if mode == "odd_days":
        return now_msk.day % 2 == 1
    if mode == "monthly":
        return now_msk.day == schedule.get("day_of_month", 1)

    return False


def schedule_to_human(schedule: dict[str, Any]) -> str:
    """Format a structured schedule as a human-readable Russian string."""
    hour = schedule.get("hour", 20)
    minute = schedule.get("minute", 0)
    mode = schedule.get("mode", "daily")
    time_str = f"{hour}:{minute:02d}"

    day_names = {
        0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг",
        4: "пятница", 5: "суббота", 6: "воскресенье",
    }

    if mode == "daily":
        return f"каждый день в {time_str} МСК"
    if mode == "weekdays":
        return f"по будням в {time_str} МСК"
    if mode == "weekends":
        return f"по выходным в {time_str} МСК"
    if mode == "specific_days":
        days = schedule.get("days_of_week", [])
        names = [day_names.get(d, "?") for d in sorted(days)]
        return f"по {', '.join(names)} в {time_str} МСК"
    if mode == "even_days":
        return f"в чётные дни в {time_str} МСК"
    if mode == "odd_days":
        return f"в нечётные дни в {time_str} МСК"
    if mode == "monthly":
        dom = schedule.get("day_of_month", 1)
        return f"{dom}-го числа каждого месяца в {time_str} МСК"

    return f"в {time_str} МСК"
