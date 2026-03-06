from __future__ import annotations
import logging

from aiogram import Router
from aiogram.types import CallbackQuery

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query()
async def unhandled_callback(callback: CallbackQuery):
    """Catch-all for unhandled callback queries."""
    logger.warning("Unhandled callback: %s from user %s", callback.data, callback.from_user.id)
    await callback.answer()
