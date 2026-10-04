from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from quintessa.models import UXRequest, UXResponse


@dataclass
class StepOutcome:
    """What a capability step produced. When `pending_ux` is set the loop
    pauses until the user answers, then calls `on_answer` to finish the step."""

    output: dict[str, Any]
    summary: str
    model: str = ""
    pending_ux: UXRequest | None = None
    on_answer: Callable[[UXResponse], Awaitable[StepOutcome]] | None = None
