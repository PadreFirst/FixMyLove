from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db.operations import get_stale_sessions
from db.mongo import get_db
from services.schedule_parser import parse_schedule, should_send_now
from services.summarizer import summarize_and_close_session

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")

_scheduler: AsyncIOScheduler | None = None
_bot_ref = None

REMINDER_TICK_MINUTES = 2
RECENT_ACTIVITY_GUARD_MINUTES = 30


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
        minutes=REMINDER_TICK_MINUTES,
        id="diary_reminders",
    )
    _scheduler.start()
    logger.info("Scheduler started (reminders every %d min)", REMINDER_TICK_MINUTES)


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


async def _ensure_parsed_schedule(user_doc: dict) -> dict | None:
    """If diary_schedule_parsed is missing but raw diary_schedule exists, parse and persist it."""
    parsed = user_doc.get("diary_schedule_parsed")
    if parsed:
        return parsed

    raw = user_doc.get("diary_schedule", "")
    if not raw:
        return None

    parsed = await parse_schedule(raw)
    if parsed:
        user_id = user_doc.get("user_id")
        db = get_db()
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"diary_schedule_parsed": parsed}},
        )
        logger.info("Migrated schedule for user %s: %s → %s", user_id, raw, parsed)
    return parsed


def _already_sent_today(last_reminder: datetime | None, now_msk: datetime) -> bool:
    """True if a reminder was already sent on the same MSK calendar date."""
    if not last_reminder:
        return False
    if last_reminder.tzinfo is None:
        last_reminder = last_reminder.replace(tzinfo=timezone.utc)
    last_msk = last_reminder.astimezone(MSK)
    return last_msk.date() == now_msk.date()


def _recently_active(last_msg_time: datetime | None, now_utc: datetime) -> bool:
    """True if user sent a message within the short guard window."""
    if not last_msg_time:
        return False
    if last_msg_time.tzinfo is None:
        last_msg_time = last_msg_time.replace(tzinfo=timezone.utc)
    delta = (now_utc - last_msg_time).total_seconds() / 60
    return delta < RECENT_ACTIVITY_GUARD_MINUTES


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


async def send_diary_reminders():
    """Cron: send diary reminders per user's structured schedule (Moscow time)."""
    try:
        db = get_db()
        now_utc = datetime.now(timezone.utc)
        now_msk = datetime.now(MSK)

        cursor = db.users.find({
            "diary_enabled": True,
            "diary_schedule": {"$ne": ""},
        })

        async for user_doc in cursor:
            user_id = user_doc.get("user_id")
            dynamic = user_doc.get("dynamic", {})

            try:
                schedule = await _ensure_parsed_schedule(user_doc)
                if not schedule:
                    continue

                if not should_send_now(schedule, now_msk, tolerance_minutes=REMINDER_TICK_MINUTES):
                    continue

                last_reminder = _parse_dt(dynamic.get("last_reminder_time"))
                if _already_sent_today(last_reminder, now_msk):
                    continue

                last_msg = _parse_dt(dynamic.get("last_message_time"))
                if _recently_active(last_msg, now_utc):
                    continue

                if _bot_ref:
                    await _bot_ref.send_message(
                        chat_id=int(user_id),
                        text="Привет! Как дела? Если есть что записать в дневник или хочешь поговорить — я здесь.",
                    )
                    await db.users.update_one(
                        {"user_id": user_id},
                        {"$set": {"dynamic.last_reminder_time": now_utc}},
                    )
                    logger.info(
                        "Sent diary reminder to %s at MSK %s (schedule: %s)",
                        user_id, now_msk.strftime("%a %H:%M"), schedule,
                    )
            except Exception as e:
                logger.error("Failed to process reminder for %s: %s", user_id, e)
    except Exception as e:
        logger.error("send_diary_reminders error: %s", e)
