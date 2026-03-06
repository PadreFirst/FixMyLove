from __future__ import annotations
from typing import Any

from db.operations import add_diary_entry, get_diary_entries
from utils.text import parse_diary_show_count


async def handle_diary_update(user_id: str, text: str) -> str:
    """Save diary entry and confirm."""
    clean = text.strip()
    for prefix in ["/diary", "запиши в дневник", "дневник", "внеси запись", "добавь в дневник"]:
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):].strip()
            break

    if not clean:
        return "Что записать в дневник? Напиши текст."

    await add_diary_entry(user_id, clean, source="user")
    return "Записал. Хочешь обсудить?"


async def handle_diary_show(user_id: str, text: str) -> str:
    """Show diary entries."""
    count = parse_diary_show_count(text)
    entries = await get_diary_entries(user_id, count)

    if not entries:
        return "В дневнике пока пусто. Можешь добавить запись командой /diary или просто написав «запиши в дневник»."

    lines = ["📓 <b>Дневник</b>\n"]
    for entry in entries:
        date = entry.get("date", "")
        if isinstance(date, str) and len(date) > 10:
            date = date[:10]
        source = " (авто)" if entry.get("source") == "auto" else ""
        lines.append(f"<b>{date}</b>{source}\n{entry.get('text', '')}\n")

    return "\n".join(lines)
