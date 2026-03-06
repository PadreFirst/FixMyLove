from __future__ import annotations
import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from config import DEBOUNCE_SECONDS
from utils.text import has_crisis_markers

logger = logging.getLogger(__name__)


class DebounceMiddleware(BaseMiddleware):
    """Accumulate rapid-fire messages and process as one batch after a delay.

    Exception: crisis markers bypass debounce and process immediately.
    """

    def __init__(self):
        super().__init__()
        self._pending: Dict[int, list[str]] = {}
        self._timers: Dict[int, asyncio.Task] = {}
        self._handlers: Dict[int, tuple[Callable, Message]] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.text:
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else 0
        text = event.text

        if has_crisis_markers(text):
            if user_id in self._timers:
                self._timers[user_id].cancel()
                pending = self._pending.pop(user_id, [])
                if pending:
                    combined = "\n---\n".join(pending + [text])
                    event._text = combined
                del self._timers[user_id]
                self._handlers.pop(user_id, None)
            return await handler(event, data)

        self._pending.setdefault(user_id, []).append(text)
        self._handlers[user_id] = (handler, data)

        if user_id in self._timers:
            self._timers[user_id].cancel()

        self._timers[user_id] = asyncio.create_task(
            self._flush_after_delay(user_id, event)
        )

    async def _flush_after_delay(self, user_id: int, event: Message):
        try:
            await asyncio.sleep(DEBOUNCE_SECONDS)
        except asyncio.CancelledError:
            return

        messages = self._pending.pop(user_id, [])
        handler_data = self._handlers.pop(user_id, None)
        self._timers.pop(user_id, None)

        if not messages or not handler_data:
            return

        handler, data = handler_data
        combined = "\n---\n".join(messages)

        event._text = combined

        try:
            await handler(event, data)
        except Exception as e:
            logger.error("Debounce flush error for user %d: %s", user_id, e)
