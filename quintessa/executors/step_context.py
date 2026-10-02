from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from quintessa.models import Capability, ReasoningSession, StepDecision

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime


@dataclass
class StepContext:
    runtime: "AgentRuntime"
    session: ReasoningSession
    capability: Capability
    decision: StepDecision
