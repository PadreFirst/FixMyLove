from __future__ import annotations
import logging
from typing import Any

from ai.response import generate_crisis_response
from db.operations import get_last_messages

logger = logging.getLogger(__name__)


async def handle_crisis(
    user_id: str,
    user_message: str,
    user: dict[str, Any],
    crisis_type: str = "suicidal",
) -> str:
    """Section 7 — handle crisis (suicidal or abuse markers)."""
    last_msgs = await get_last_messages(user_id, count=10)
    return await generate_crisis_response(user_message, user, crisis_type, last_msgs)
