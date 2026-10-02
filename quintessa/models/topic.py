from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now
from quintessa.models.trigger_spec import TriggerSpec


@dataclass
class Topic:
    """An entry in the index of the user's world (a "card"). Topics nest via
    parent_id and carry the metadata the agent uses to decide when to show them."""

    id: str
    title: str
    category: str = ""
    parent_id: str | None = None
    summary: str = ""
    new_info: str = ""
    importance: str = ""
    progress: float = 0.0
    progress_note: str = ""
    due: str = ""
    triggers: list[TriggerSpec] = field(default_factory=list)
    document_id: str | None = None
    archived: bool = False
    last_seen_at: datetime | None = None
    updated_at: datetime = field(default_factory=now)
