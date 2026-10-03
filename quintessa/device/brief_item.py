from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import new_id, now
from quintessa.device.salience import Salience

# The event behind the reasoning session now writing cards. Each session runs
# in its own task, so cards it writes remember what caused them.
BRIEF_SOURCE: ContextVar[str | None] = ContextVar("brief_source", default=None)


@dataclass
class BriefAction:
    """Something the user can start from a brief card with one tap, like
    "Call Mom". The tap starts a reasoning session that already holds the
    user's approval for this one tool function."""

    tool: str
    function: str
    label: str
    arguments: dict[str, str] = field(default_factory=dict)


@dataclass
class BriefItem:
    """One glanceable call to action in the contextual brief. Tapping it opens
    the topic's document (or pending question) in Spaces, focused on the
    section it is about. A card with no document opens a sheet with its
    detail, its topic, its open questions and its action.

    A card is a snapshot of what was true when it was written, so it keeps
    when that was and what caused it. It is stale once its topic changes
    after `updated_at`, and the device drops it at `expires_at`. The brief is
    ordered by `salience` (see salience.py); `due_at` is when the thing the
    card is about happens, which drives its time proximity."""

    text: str
    topic_id: str | None = None
    document_id: str | None = None
    section_id: str | None = None
    ux_request_id: str | None = None
    urgency: str = "normal"
    detail: str = ""
    action: BriefAction | None = None
    expires_at: datetime | None = None
    due_at: datetime | None = None
    salience: Salience = field(default_factory=Salience)
    opened_at: datetime | None = None  # the user last opened the card
    snoozed_until: datetime | None = None
    source_event_id: str | None = field(default_factory=BRIEF_SOURCE.get)
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)
    id: str = field(default_factory=lambda: new_id("brf"))

    def expired(self, at: datetime) -> bool:
        return self.expires_at is not None and self.expires_at <= at
