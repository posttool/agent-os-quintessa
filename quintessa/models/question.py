from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import new_id, now
from quintessa.models.question_field import QuestionField
from quintessa.models.question_purpose import QuestionPurpose


@dataclass
class Question:
    """Generated UI the reasoning loop waits on. It remembers the context that
    produced it so the answer returns to that context (a document section,
    a pending tool call) and so a brief card for its topic can show it."""

    session_id: str
    purpose: QuestionPurpose
    prompt: str
    fields: list[QuestionField] = field(default_factory=list)
    document_id: str | None = None
    section_id: str | None = None
    tool: str | None = None
    function: str | None = None
    topic_id: str | None = None
    # why the agent asks, in one sentence; for an approval, the call it runs
    context: str = ""
    arguments: dict[str, str] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("q"))
    created_at: datetime = field(default_factory=now)
