from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import new_id, now
from quintessa.models.input_kind import InputKind


@dataclass
class InputEvent:
    """Anything that can trigger a reasoning session. Raw events are kept for
    auditing; memory organizes what they mean."""

    kind: InputKind
    content: str
    source: str = "user"
    device: str = ""
    sender: str = ""
    subscription_id: str | None = None
    id: str = field(default_factory=lambda: new_id("evt"))
    occurred_at: datetime = field(default_factory=now)
