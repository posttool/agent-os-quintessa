from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from quintessa.models import Answer, Question


@dataclass
class StepOutcome:
    """What a capability step produced. When `question` is set the loop
    pauses until the user answers, then calls `on_answer` to finish the step."""

    output: dict[str, Any]
    summary: str
    model: str = ""
    question: Question | None = None
    on_answer: Callable[[Answer], Awaitable[StepOutcome]] | None = None
