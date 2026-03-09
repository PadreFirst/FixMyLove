from __future__ import annotations
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db.operations import get_stale_sessions, get_user
from db.mongo import get_db
from services.summarizer import summarize_and_close_session

logger = logging.getLogger(__name__)

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


async def send_diary_reminders():
    """Cron: send diary reminders per user schedule."""
    try:
        db = get_db()
        now = datetime.now(timezone.utc)
        cursor = db.users.find({
            "diary_enabled": True,
            "diary_schedule": {"$ne": ""},
        })

        async for user_doc in cursor:
            user_id = user_doc.get("user_id")
            dynamic = user_doc.get("dynamic", {})
            last_time = dynamic.get("last_message_time")

            if last_time:
                if isinstance(last_time, str):
                    try:
                        from datetime import datetime as dt
                        last_time = dt.fromisoformat(last_time)
                    except ValueError:
                        last_time = None

                if last_time:
                    hours_since = (now - last_time).total_seconds() / 3600
                    if hours_since < 24:
                        continue

            # Skip if we already sent a reminder recently (within 23h)
            last_reminder = dynamic.get("last_reminder_time")
            if last_reminder:
                if isinstance(last_reminder, str):
                    try:
                        from datetime import datetime as dt
                        last_reminder = dt.fromisoformat(last_reminder)
                    except ValueError:
                        last_reminder = None
                if last_reminder:
                    hours_since_reminder = (now - last_reminder).total_seconds() / 3600
                    if hours_since_reminder < 23:
                        continue

            if _bot_ref:
                try:
                    await _bot_ref.send_message(
                        chat_id=int(user_id),
                        text="Привет! Как дела? Если есть что записать в дневник или хочешь поговорить — я здесь.",
                    )
                    # Mark reminder as sent so we don't spam
                    await db.users.update_one(
                        {"user_id": user_id},
                        {"$set": {"dynamic.last_reminder_time": now}},
                    )
                    logger.info("Sent diary reminder to %s", user_id)
                except Exception as e:
                    logger.error("Failed to send reminder to %s: %s", user_id, e)
    except Exception as e:
        logger.error("send_diary_reminders error: %s", e)
