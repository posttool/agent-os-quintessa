from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now
from quintessa.models.node_type import NodeType


@dataclass
class MemoryNode:
    """A fact or process in the shared memory graph."""

    id: str
    type: NodeType
    title: str
    body: str = ""
    topic_id: str | None = None
    source_event_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)
