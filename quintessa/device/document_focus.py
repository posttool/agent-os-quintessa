from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from quintessa.clock import now


class ViewMode(StrEnum):
    FOCUSED = "focused"  # only the sections that matter now; the rest fold into an outline
    FULL = "full"  # the whole document


class FocusSource(StrEnum):
    """Who chose what Spaces shows."""

    AGENT = "agent"  # the device tool or an answered question
    USER = "user"  # a tap or an ask
    RULE = "rule"  # pinned when the user first looks


FOCUSED, FULL = ViewMode.FOCUSED, ViewMode.FULL


@dataclass
class DocumentFocus:
    """Which parts of a document Spaces shows expanded. The rest of the
    document folds into an outline the user can open on demand."""

    document_id: str
    section_ids: list[str] = field(default_factory=list)
    mode: ViewMode = ViewMode.FOCUSED
    reason: str = ""
    set_by: FocusSource = FocusSource.AGENT
    updated_at: datetime = field(default_factory=now)
