from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now
from quintessa.models.selection import Selection


@dataclass
class Answer:
    """The user's answer to a question. A question the agent takes back before
    the user answers (the news answered it) comes back `withdrawn`, with why."""

    question_id: str
    values: dict[str, str] = field(default_factory=dict)
    # what was picked in each multi_option field, with quantities; `values`
    # holds the same as text ("2 × Margherita, Coke")
    selections: dict[str, list[Selection]] = field(default_factory=dict)
    dismissed: bool = False
    surface_context: str = ""  # where it was answered
    withdrawn: bool = False
    withdrawn_reason: str = ""
    answered_at: datetime = field(default_factory=now)
