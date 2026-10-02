from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCallResult:
    status: str  # done | in_progress | needs_user | failed
    result: str
    progress_stages: list[str] = field(default_factory=list)
