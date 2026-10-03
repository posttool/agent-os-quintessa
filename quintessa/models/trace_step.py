from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from quintessa.clock import now


@dataclass
class TraceStep:
    index: int
    capability: str
    focus: str
    rationale: str
    output: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    model: str = ""
    error: str = ""
    decided_by: str = ""  # "jev" when Jev picked this step; empty when the LLM did
    started_at: datetime = field(default_factory=now)
    ended_at: datetime | None = None
