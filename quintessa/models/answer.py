from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now

# surface_context of a question the agent took back before the user answered
WITHDRAWN = "withdrawn: "


@dataclass
class Answer:
    question_id: str
    values: dict[str, str] = field(default_factory=dict)
    dismissed: bool = False
    surface_context: str = ""
    answered_at: datetime = field(default_factory=now)
