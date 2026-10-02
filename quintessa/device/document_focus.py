from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now

FOCUSED = "focused"
FULL = "full"


@dataclass
class DocumentFocus:
    """Which parts of a document Spaces shows expanded. The rest of the
    document folds into an outline the user can open on demand.

    `set_by` is "agent" (the device tool or an answered question), "user"
    (a tap or an ask) or "rule" (pinned when the user first looks)."""

    document_id: str
    section_ids: list[str] = field(default_factory=list)
    mode: str = FOCUSED
    reason: str = ""
    set_by: str = "agent"
    updated_at: datetime = field(default_factory=now)
