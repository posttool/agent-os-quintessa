from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import new_id, now


@dataclass
class Subscription:
    """An ambient stream watching a long-running real-world process (a taxi,
    a delivery) so progress comes back into the loop as events."""

    tool: str
    function: str
    description: str
    stages: list[str] = field(default_factory=list)
    next_stage: int = 0
    document_id: str | None = None
    section_id: str | None = None
    archived: bool = False
    id: str = field(default_factory=lambda: new_id("sub"))
    created_at: datetime = field(default_factory=now)

    @property
    def complete(self) -> bool:
        return self.next_stage >= len(self.stages)
