from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any

from db.mongo import get_db
from db.models import StaticProfile, empty_dynamic, new_session_dynamic, _utcnow
from config import SLIDING_WINDOW_SIZE, SESSION_TIMEOUT_HOURS


def _uid(user_id: int | str) -> str:
    return str(user_id)


async def get_or_create_user(user_id: int | str) -> dict[str, Any]:
    uid = _uid(user_id)
    db = get_db()
    doc = await db.users.find_one({"user_id": uid})
    if doc:
        return doc
    profile = StaticProfile(user_id=uid)
    data = profile.model_dump()
    data["dynamic"] = empty_dynamic()
    await db.users.insert_one(data)
    return await db.users.find_one({"user_id": uid})


async def get_user(user_id: int | str) -> dict[str, Any] | None:
    return await get_db().users.find_one({"user_id": _uid(user_id)})


async def update_user(user_id: int | str, update: dict[str, Any]):
    await get_db().users.update_one({"user_id": _uid(user_id)}, {"$set": update})


async def update_static_field(user_id: int | str, field: str, value: Any):
    await get_db().users.update_one({"user_id": _uid(user_id)}, {"$set": {field: value}})


async def update_dynamic_field(user_id: int | str, field: str, value: Any):
    await get_db().users.update_one(
        {"user_id": _uid(user_id)}, {"$set": {f"dynamic.{field}": value}}
    )


async def update_dynamic(user_id: str, updates: dict[str, Any]):
    sets = {f"dynamic.{k}": v for k, v in updates.items()}
    await get_db().users.update_one({"user_id": user_id}, {"$set": sets})


async def push_to_sliding_window(user_id: str, role: str, text: str):
    entry = {"role": role, "text": text, "ts": _utcnow().isoformat()}
    db = get_db()
    await db.users.update_one(
        {"user_id": user_id}, {"$push": {"dynamic.sliding_window": entry}}
    )
    user = await db.users.find_one({"user_id": user_id})
    window = user.get("dynamic", {}).get("sliding_window", [])
    if len(window) > SLIDING_WINDOW_SIZE:
        trimmed = window[-SLIDING_WINDOW_SIZE:]
        await db.users.update_one(
            {"user_id": user_id}, {"$set": {"dynamic.sliding_window": trimmed}}
        )


async def get_last_messages(user_id: str, count: int = 3) -> list[dict[str, str]]:
    user = await get_user(user_id)
    if not user:
        return []
    window = user.get("dynamic", {}).get("sliding_window", [])
    return window[-count:] if window else []


async def add_session_summary(user_id: str, summary: dict[str, Any]):
    await get_db().users.update_one(
        {"user_id": user_id}, {"$push": {"session_summaries": summary}}
    )


async def get_last_summaries(user_id: str, count: int = 3) -> list[dict[str, Any]]:
    user = await get_user(user_id)
    if not user:
        return []
    summaries = user.get("session_summaries", [])
    return summaries[-count:]


async def add_diary_entry(user_id: str, text: str, source: str = "user"):
    entry = {"date": _utcnow().isoformat(), "text": text, "source": source}
    await get_db().users.update_one(
        {"user_id": user_id}, {"$push": {"diary_entries": entry}}
    )


async def get_diary_entries(user_id: str, count: int = 10) -> list[dict[str, Any]]:
    user = await get_user(user_id)
    if not user:
        return []
    entries = user.get("diary_entries", [])
    return entries[-count:]


async def add_important_fact(user_id: str, fact: str):
    """Add a fact with timestamps. If a similar text already exists, update last_confirmed."""
    uid = _uid(user_id)
    now = _utcnow().isoformat()
    fact_text = fact.strip()
    if not fact_text:
        return

    user = await get_db().users.find_one({"user_id": uid})
    if not user:
        return

    existing = user.get("important_facts", [])

    # Backward compat: migrate old string-only facts
    migrated = []
    for f in existing:
        if isinstance(f, str):
            migrated.append({"text": f, "first_seen": now, "last_confirmed": now})
        else:
            migrated.append(f)

    # Check for exact text match — update last_confirmed
    found = False
    for item in migrated:
        if item.get("text", "").strip().lower() == fact_text.lower():
            item["last_confirmed"] = now
            found = True
            break

    if not found:
        migrated.append({"text": fact_text, "first_seen": now, "last_confirmed": now})

    await get_db().users.update_one(
        {"user_id": uid}, {"$set": {"important_facts": migrated}}
    )


async def add_session_fact(user_id: str, fact: str):
    await get_db().users.update_one(
        {"user_id": user_id}, {"$push": {"dynamic.session_facts": fact}}
    )


async def add_detected_pattern(user_id: str, pattern: str):
    await get_db().users.update_one(
        {"user_id": user_id}, {"$addToSet": {"detected_patterns": pattern}}
    )


async def open_new_session(user_id: str) -> str:
    data = new_session_dynamic()
    await update_user(user_id, {"dynamic": data})
    return data["session_id"]


async def close_session(user_id: str):
    await update_user(user_id, {"dynamic": empty_dynamic()})


async def get_stale_sessions() -> list[dict[str, Any]]:
    db = get_db()
    cutoff = _utcnow() - timedelta(hours=SESSION_TIMEOUT_HOURS)
    cursor = db.users.find({
        "dynamic.session_open": True,
        "dynamic.last_message_time": {"$lt": cutoff},
    })
    return await cursor.to_list(length=500)


async def archive_partner(user_id: str):
    user = await get_user(user_id)
    if not user:
        return
    archive_entry = {
        "partner_name": user.get("partner_name", ""),
        "partner_age": user.get("partner_age"),
        "partner_gender": user.get("partner_gender", "unknown"),
        "shadow_profile_partner": user.get("shadow_profile_partner", ""),
        "detected_patterns": user.get("detected_patterns", []),
        "archived_at": _utcnow().isoformat(),
    }
    await get_db().users.update_one(
        {"user_id": user_id},
        {
            "$push": {"archived_partners": archive_entry},
            "$set": {
                "partner_name": "",
                "partner_age": None,
                "partner_gender": "unknown",
                "shadow_profile_partner": "",
                "detected_patterns": [],
                "dynamic": empty_dynamic(),
            },
        },
    )


async def delete_user(user_id: str):
    await get_db().users.delete_one({"user_id": user_id})


async def update_last_message_time(user_id: str):
    await update_dynamic_field(user_id, "last_message_time", _utcnow())


async def append_shadow_profile(user_id: str, user_update: str, partner_update: str):
    user = await get_user(user_id)
    if not user:
        return
    current_user = user.get("shadow_profile_user", "")
    current_partner = user.get("shadow_profile_partner", "")

    if user_update.strip():
        new_user = f"{current_user} {user_update}".strip() if current_user else user_update
        await update_static_field(user_id, "shadow_profile_user", new_user)

    if partner_update.strip():
        new_partner = f"{current_partner} {partner_update}".strip() if current_partner else partner_update
        await update_static_field(user_id, "shadow_profile_partner", new_partner)
