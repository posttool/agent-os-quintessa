from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import new_id, now
from quintessa.models.ux_field import UXField
from quintessa.models.ux_purpose import UXPurpose


@dataclass
class UXRequest:
    """Generated UI the reasoning loop waits on. It remembers the context that
    produced it so the answer returns to that context (a document section,
    a pending tool call) and so a brief card for its topic can show it."""

    session_id: str
    purpose: UXPurpose
    prompt: str
    fields: list[UXField] = field(default_factory=list)
    document_id: str | None = None
    section_id: str | None = None
    tool: str | None = None
    function: str | None = None
    topic_id: str | None = None
    # why the agent asks, in one sentence; for an approval, the call it runs
    context: str = ""
    arguments: dict[str, str] = field(default_factory=dict)
    # asked by a session the user started moments ago, so they are likely
    # looking at the screen; a skin may open the question at once
    user_waiting: bool = False
    id: str = field(default_factory=lambda: new_id("ux"))
    created_at: datetime = field(default_factory=now)
