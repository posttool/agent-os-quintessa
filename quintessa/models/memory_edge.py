from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now
from quintessa.models.edge_type import EdgeType


@dataclass
class MemoryEdge:
    source_id: str
    target_id: str
    type: EdgeType
    note: str = ""
    created_at: datetime = field(default_factory=now)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source_id, self.target_id, self.type.value)
