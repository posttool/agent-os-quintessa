from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now
from quintessa.models.picture import Picture


@dataclass
class DocumentSection:
    id: str
    title: str
    overview: str = ""
    status: str = ""
    details: str = ""
    actions_taken: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    # good pictures of what the user chose in a question about this
    pictures: list[Picture] = field(default_factory=list)
    updated_at: datetime = field(default_factory=now)
