from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now


@dataclass
class Answer:
    """The user's answer to a question. A question the agent takes back before
    the user answers (the news answered it) comes back `withdrawn`, with why."""

    question_id: str
    values: dict[str, str] = field(default_factory=dict)
    dismissed: bool = False
    surface_context: str = ""  # where it was answered
    withdrawn: bool = False
    withdrawn_reason: str = ""
    answered_at: datetime = field(default_factory=now)
