from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field
import uuid


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_session_id() -> str:
    return uuid.uuid4().hex[:12]


class DiaryEntry(BaseModel):
    date: datetime = Field(default_factory=_utcnow)
    text: str
    source: str = "user"


class SessionSummary(BaseModel):
    session_id: str
    date: datetime = Field(default_factory=_utcnow)
    situation_type: str = ""
    user_request: str = ""
    dominant_pattern: str = ""
    initiator: str = ""
    final_phase: str = ""
    user_action: str = ""
    pending_task: str = "-"
    new_partner_data: str = "-"
    mood_in: int | None = None
    mood_out: int | None = None
    shadow_user_update: str = ""
    shadow_partner_update: str = ""


class ArchivedPartner(BaseModel):
    partner_name: str = ""
    partner_age: int | None = None
    partner_gender: str = "unknown"
    shadow_profile_partner: str = ""
    detected_patterns: list[str] = Field(default_factory=list)
    archived_at: datetime = Field(default_factory=_utcnow)


class StaticProfile(BaseModel):
    user_id: str
    name: str = ""
    gender: str = "unknown"
    age: int | None = None
    partner_name: str = ""
    partner_age: int | None = None
    partner_gender: str = "unknown"
    relationship_status: str = ""
    relationship_duration: int | None = None
    relationship_note: str = ""
    attachment_style: str = ""
    diary_enabled: bool = False
    diary_schedule: str = ""
    diary_schedule_parsed: dict[str, Any] | None = None
    session_summaries: list[dict[str, Any]] = Field(default_factory=list)
    diary_entries: list[dict[str, Any]] = Field(default_factory=list)
    detected_patterns: list[str] = Field(default_factory=list)
    mood_history: list[int | None] = Field(default_factory=list)
    shadow_profile_user: str = ""
    shadow_profile_partner: str = ""
    archived_partners: list[dict[str, Any]] = Field(default_factory=list)
    onboarding_complete: bool = False
    important_facts: list[dict[str, Any]] = Field(default_factory=list)
    privacy_accepted: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class DynamicProfile(BaseModel):
    session_open: bool = False
    session_id: str = ""
    situation_type: str = ""
    user_goal: str = ""
    initiator: str = ""
    dominant_pattern: str = ""
    methodology: str = ""
    current_phase: str = ""
    current_request: str = ""
    tone: str = ""
    is_acute: bool = False
    session_facts: list[str] = Field(default_factory=list)
    pending_task: str = ""
    last_message_time: datetime | None = None
    sliding_window: list[dict[str, str]] = Field(default_factory=list)
    off_topic_count: int = 0
    phase_message_count: int = 0
    session_message_count: int = 0


def empty_dynamic() -> dict[str, Any]:
    return DynamicProfile().model_dump()


def new_session_dynamic(session_id: str | None = None) -> dict[str, Any]:
    return DynamicProfile(
        session_open=True,
        session_id=session_id or _new_session_id(),
        last_message_time=_utcnow(),
    ).model_dump()
