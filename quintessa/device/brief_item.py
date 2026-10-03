from __future__ import annotations

from dataclasses import dataclass, field

from quintessa.clock import new_id


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
    detail, its topic, its open questions and its action."""

    text: str
    topic_id: str | None = None
    document_id: str | None = None
    section_id: str | None = None
    ux_request_id: str | None = None
    urgency: str = "normal"
    detail: str = ""
    action: BriefAction | None = None
    id: str = field(default_factory=lambda: new_id("brf"))
