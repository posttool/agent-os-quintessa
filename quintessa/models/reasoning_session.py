from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import new_id, now
from quintessa.models.input_event import InputEvent
from quintessa.models.permission import Permission
from quintessa.models.session_status import SessionStatus
from quintessa.models.shadow_decision import ShadowDecision
from quintessa.models.trace_step import TraceStep


@dataclass
class ReasoningSession:
    """One run of the reasoning loop, started by one trigger. Its steps are
    the trace; its permissions carry forward to later steps in the chain."""

    trigger: InputEvent
    status: SessionStatus = SessionStatus.RUNNING
    steps: list[TraceStep] = field(default_factory=list)
    permissions: list[Permission] = field(default_factory=list)
    shadow_decisions: list[ShadowDecision] = field(default_factory=list)
    pending_ux_id: str | None = None
    id: str = field(default_factory=lambda: new_id("ses"))
    started_at: datetime = field(default_factory=now)
    ended_at: datetime | None = None
