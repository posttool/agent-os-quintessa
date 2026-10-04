from __future__ import annotations

from dataclasses import dataclass, field

from quintessa.models.tool_call_status import ToolCallStatus


@dataclass
class ToolCallResult:
    status: ToolCallStatus
    result: str
    progress_stages: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.status = ToolCallStatus(self.status)  # simulated tools answer with the plain value
