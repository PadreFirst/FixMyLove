from __future__ import annotations
import asyncio
import logging
from typing import Optional

from aiogram import Bot
from aiogram.enums import ChatAction

logger = logging.getLogger(__name__)


class TypingKeeper:
    """Keeps the "typing..." indicator alive while the bot is generating a response.

    Telegram auto-clears the indicator after ~5 seconds, so we re-send it every 4s.
    Usage:
        async with TypingKeeper(bot, chat_id):
            response = await long_running_generation(...)
    """

    def __init__(self, bot: Bot, chat_id: int, interval: float = 4.0):
        self._bot = bot
        self._chat_id = chat_id
        self._interval = interval
        self._task: Optional[asyncio.Task] = None

    async def __aenter__(self):
        await self._send_once()
        self._task = asyncio.create_task(self._loop())
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return False

    async def _send_once(self):
        try:
            await self._bot.send_chat_action(chat_id=self._chat_id, action=ChatAction.TYPING)
        except Exception as e:
            logger.debug("send_chat_action failed: %s", e)

    async def _loop(self):
        try:
            while True:
                await asyncio.sleep(self._interval)
                await self._send_once()
        except asyncio.CancelledError:
            return
