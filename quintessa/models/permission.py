from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now
from quintessa.models.permission_scope import PermissionScope


@dataclass
class Permission:
    """A user's answer at a decision boundary. Session-scoped grants carry
    forward through the rest of a reasoning session; persistent ones are kept
    in memory for future reasoning."""

    tool: str
    function: str
    granted: bool
    scope: PermissionScope
    detail: str = ""
    session_id: str | None = None
    question_id: str | None = None
    granted_at: datetime = field(default_factory=now)
