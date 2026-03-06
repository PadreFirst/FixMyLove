from __future__ import annotations
import time
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from config import RATE_LIMIT_PER_HOUR, RATE_LIMIT_BLOCK_MINUTES

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """Limit messages per user: max RATE_LIMIT_PER_HOUR messages/hour.

    When exceeded, block for RATE_LIMIT_BLOCK_MINUTES and send a message.
    """

    def __init__(self):
        super().__init__()
        self._counts: Dict[int, list[float]] = {}
        self._blocked_until: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else 0
        now = time.time()

        blocked_until = self._blocked_until.get(user_id, 0)
        if now < blocked_until:
            return None

        if now >= blocked_until and user_id in self._blocked_until:
            del self._blocked_until[user_id]
            self._counts.pop(user_id, None)

        timestamps = self._counts.get(user_id, [])
        cutoff = now - 3600
        timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= RATE_LIMIT_PER_HOUR:
            self._blocked_until[user_id] = now + RATE_LIMIT_BLOCK_MINUTES * 60
            self._counts[user_id] = timestamps
            await event.answer(
                "Ты пишешь очень активно — давай немного притормозим. "
                "Я здесь, никуда не ухожу."
            )
            return None

        timestamps.append(now)
        self._counts[user_id] = timestamps

        return await handler(event, data)
