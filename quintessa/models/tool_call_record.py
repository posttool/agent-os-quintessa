from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now
from quintessa.models.tool_call_status import ToolCallStatus


@dataclass
class ToolCallRecord:
    """One past call to a simulated tool, kept so later calls stay
    consistent with what the tool already reported."""

    function: str
    arguments: dict[str, str] = field(default_factory=dict)
    purpose: str = ""
    status: ToolCallStatus = ToolCallStatus.DONE
    result: str = ""
    at: datetime = field(default_factory=now)
