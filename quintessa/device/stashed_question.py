from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now


@dataclass
class StashedQuestion:
    """A waiting question the user put aside. It stays unanswered (its
    session keeps waiting) but leaves the needs-you stack until the user
    opens the stash or its topic changes."""

    ux_request_id: str
    topic_id: str | None = None
    stashed_at: datetime = field(default_factory=now)
