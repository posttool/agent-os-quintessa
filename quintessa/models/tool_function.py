from __future__ import annotations

from dataclasses import dataclass, field

from quintessa.models.oversight_level import OversightLevel
from quintessa.models.tool_parameter import ToolParameter


@dataclass
class ToolFunction:
    name: str
    description: str = ""
    parameters: list[ToolParameter] = field(default_factory=list)
    returns: str = "string"
    oversight: OversightLevel = OversightLevel.AUTO
    long_running: bool = False
