from __future__ import annotations
import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db.operations import get_stale_sessions, get_user
from db.mongo import get_db
from services.summarizer import summarize_and_close_session

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")

_scheduler: AsyncIOScheduler | None = None
_bot_ref = None


def init_scheduler(bot):
    global _scheduler, _bot_ref
    _bot_ref = bot
    _scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    _scheduler.add_job(
        close_stale_sessions,
        "interval",
        hours=1,
        id="close_stale_sessions",
    )
    _scheduler.add_job(
        send_diary_reminders,
        "interval",
        hours=1,
        id="diary_reminders",
    )
    _scheduler.start()
    logger.info("Scheduler started")


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None


async def close_stale_sessions():
    """Cron: close sessions open > 24 hours with no messages."""
    try:
        stale = await get_stale_sessions()
        logger.info("Found %d stale sessions to close", len(stale))
        for user_doc in stale:
            user_id = user_doc.get("user_id")
            dynamic = user_doc.get("dynamic", {})
            window = dynamic.get("sliding_window", [])
            try:
                await summarize_and_close_session(user_id, window, dynamic)
                logger.info("Closed stale session for user %s", user_id)
            except Exception as e:
                logger.error("Error closing stale session for %s: %s", user_id, e)
    except Exception as e:
        logger.error("close_stale_sessions error: %s", e)


def _parse_schedule_hour(schedule: str) -> int | None:
    """Extract the target hour (Moscow time) from diary_schedule string.

    Supports formats: "13:00", "13", "в 13", "утром", "днём", "вечером".
    Returns None if unparseable.
    """
    s = schedule.strip().lower()

    time_match = re.search(r"(\d{1,2})[:\.\s]?(\d{2})?", s)
    if time_match:
        hour = int(time_match.group(1))
        if 0 <= hour <= 23:
            return hour

    keywords = {
        "утр": 9, "утром": 9,
        "днём": 13, "днем": 13, "обед": 13,
        "вечер": 20, "вечером": 20,
        "ночь": 22, "ночью": 22,
    }
    for kw, h in keywords.items():
        if kw in s:
            return h

    return None


async def send_diary_reminders():
    """Cron: send diary reminders per user schedule (Moscow time)."""
    try:
        db = get_db()
        now_utc = datetime.now(timezone.utc)
        now_msk = datetime.now(MSK)
        current_hour = now_msk.hour

        cursor = db.users.find({
            "diary_enabled": True,
            "diary_schedule": {"$ne": ""},
        })

        async for user_doc in cursor:
            user_id = user_doc.get("user_id")
            schedule = user_doc.get("diary_schedule", "")
            dynamic = user_doc.get("dynamic", {})

            target_hour = _parse_schedule_hour(schedule)
            if target_hour is not None and abs(current_hour - target_hour) > 1:
                continue

            last_time = dynamic.get("last_message_time")
            if last_time:
                if isinstance(last_time, str):
                    try:
                        last_time = datetime.fromisoformat(last_time)
                    except ValueError:
                        last_time = None
                if last_time:
                    if last_time.tzinfo is None:
                        last_time = last_time.replace(tzinfo=timezone.utc)
                    hours_since = (now_utc - last_time).total_seconds() / 3600
                    if hours_since < 24:
                        continue

            last_reminder = dynamic.get("last_reminder_time")
            if last_reminder:
                if isinstance(last_reminder, str):
                    try:
                        last_reminder = datetime.fromisoformat(last_reminder)
                    except ValueError:
                        last_reminder = None
                if last_reminder:
                    if last_reminder.tzinfo is None:
                        last_reminder = last_reminder.replace(tzinfo=timezone.utc)
                    hours_since_reminder = (now_utc - last_reminder).total_seconds() / 3600
                    if hours_since_reminder < 23:
                        continue

            if _bot_ref:
                try:
                    await _bot_ref.send_message(
                        chat_id=int(user_id),
                        text="Привет! Как дела? Если есть что записать в дневник или хочешь поговорить — я здесь.",
                    )
                    await db.users.update_one(
                        {"user_id": user_id},
                        {"$set": {"dynamic.last_reminder_time": now_utc}},
                    )
                    logger.info("Sent diary reminder to %s at MSK hour %d", user_id, current_hour)
                except Exception as e:
                    logger.error("Failed to send reminder to %s: %s", user_id, e)
    except Exception as e:
        logger.error("send_diary_reminders error: %s", e)
