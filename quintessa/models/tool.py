from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now
from quintessa.models.tool_function import ToolFunction
from quintessa.models.tool_kind import ToolKind


@dataclass
class Tool:
    """A group of typed functions plus how the agent may use them. `grounding`
    is the system prompt for LLM tools; `endpoint` is the URL for web API or
    MCP tools; `code` holds agent-written source for CODE tools."""

    name: str
    description: str
    kind: ToolKind
    functions: list[ToolFunction] = field(default_factory=list)
    grounding: str = ""
    endpoint: str = ""
    code: str = ""
    created_by: str = "agent"
    created_at: datetime = field(default_factory=now)

    def function(self, name: str) -> ToolFunction | None:
        return next((f for f in self.functions if f.name == name), None)
