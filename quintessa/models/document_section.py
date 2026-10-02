from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DocumentSection:
    id: str
    title: str
    overview: str = ""
    status: str = ""
    details: str = ""
    actions_taken: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    process_ids: list[str] = field(default_factory=list)
