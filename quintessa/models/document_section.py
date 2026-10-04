from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now


@dataclass
class DocumentSection:
    id: str
    title: str
    overview: str = ""
    status: str = ""
    details: str = ""
    actions_taken: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=now)
