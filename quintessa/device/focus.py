"""Decides which sections of a document Spaces shows expanded, so the user
sees what matters now instead of the whole document."""

from __future__ import annotations

from typing import Any

from quintessa.device.document_focus import FOCUSED, FULL, DocumentFocus, FocusSource
from quintessa.models import Document, Question, Topic

MAX_FOCUSED = 2
COMPLETE_STATUSES = {"complete", "completed", "done"}


def changed_sections(doc: Document, topic: Topic | None) -> list[str]:
    """Sections changed since the user last looked at the document's topic."""
    seen = topic.last_seen_at if topic else None
    if seen is None:
        return []
    return [s.id for s in doc.sections if s.updated_at > seen]


def is_stale(doc: Document, focus: DocumentFocus) -> bool:
    """A chosen focus gives way once a section outside it changes."""
    if focus.mode == FULL:
        return False
    return any(s.updated_at > focus.updated_at for s in doc.sections if s.id not in focus.section_ids)


def rule_sections(doc: Document, questions: list[Question], changed: list[str]) -> list[str]:
    """When nobody chose: sections with a waiting question, then sections
    changed since the user last looked, then the first open section with a
    next step."""
    ids = {s.id for s in doc.sections}
    picked: list[str] = []
    for sid in [q.section_id for q in questions if q.document_id == doc.id] + changed:
        if sid in ids and sid not in picked:
            picked.append(sid)
    if not picked:
        open_next = next(
            (s.id for s in doc.sections if s.suggested_actions and s.status.strip().lower() not in COMPLETE_STATUSES),
            None,
        )
        if open_next:
            picked.append(open_next)
    return picked[:MAX_FOCUSED]


def resolve_view(
    doc: Document,
    focus: DocumentFocus | None,
    questions: list[Question],
    topic: Topic | None,
) -> dict[str, Any]:
    """What Spaces shows for a document: the focused sections, the mode, why,
    and which sections changed since the user last looked."""
    changed = changed_sections(doc, topic)
    ids = {s.id for s in doc.sections}
    chosen = focus if focus and not is_stale(doc, focus) else None
    sections = [sid for sid in chosen.section_ids if sid in ids] if chosen else []
    if chosen and chosen.set_by != FocusSource.USER:
        sections = sections[:MAX_FOCUSED]  # the user may open as many as they like
    mode = chosen.mode if chosen else FOCUSED
    set_by = chosen.set_by if chosen else FocusSource.RULE
    if mode == FOCUSED and not sections and set_by != FocusSource.USER:
        sections, set_by = rule_sections(doc, questions, changed), FocusSource.RULE
    return {
        "document_id": doc.id,
        "section_ids": sections,
        "mode": mode,
        "reason": chosen.reason if chosen else "",
        "set_by": set_by,
        "changed_section_ids": changed,
    }
