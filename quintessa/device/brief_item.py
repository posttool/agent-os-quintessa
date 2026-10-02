from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BriefItem:
    """One glanceable call to action in the contextual brief. Tapping it opens
    the topic's document (or pending question) in Spaces."""

    text: str
    topic_id: str | None = None
    document_id: str | None = None
    ux_request_id: str | None = None
    urgency: str = "normal"
