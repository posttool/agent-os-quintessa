from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now


@dataclass
class UXResponse:
    request_id: str
    values: dict[str, str] = field(default_factory=dict)
    dismissed: bool = False
    surface_context: str = ""
    answered_at: datetime = field(default_factory=now)
