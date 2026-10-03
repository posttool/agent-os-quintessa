from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now
from quintessa.models.app_listing import AppListing
from quintessa.models.auth_requirement import AuthRequirement
from quintessa.models.tool_binding import ToolBinding
from quintessa.models.tool_call_record import ToolCallRecord
from quintessa.models.tool_function import ToolFunction
from quintessa.models.tool_kind import ToolKind


@dataclass
class Tool:
    """A group of typed functions plus how the agent may use them. `grounding`
    is the system prompt for LLM tools; `endpoint` is the URL for web API or
    MCP tools; `code` holds agent-written source for CODE tools.

    APP tools are installed from an app store: `listing` is what the store
    said, `binding` how calls run and `auth` what sign-in they would need.

    `history` holds recent calls to a simulated tool, so the model playing
    it answers consistently with what it reported before."""

    name: str
    description: str
    kind: ToolKind
    functions: list[ToolFunction] = field(default_factory=list)
    grounding: str = ""
    endpoint: str = ""
    code: str = ""
    created_by: str = "agent"
    created_at: datetime = field(default_factory=now)
    listing: AppListing | None = None
    binding: ToolBinding = ToolBinding.SIMULATED
    auth: AuthRequirement = field(default_factory=AuthRequirement)
    history: list[ToolCallRecord] = field(default_factory=list)

    def function(self, name: str) -> ToolFunction | None:
        return next((f for f in self.functions if f.name == name), None)
