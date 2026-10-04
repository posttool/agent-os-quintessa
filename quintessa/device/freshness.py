"""Whether brief cards still hold, and the brief as the agent reads it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from quintessa.clock import now
from quintessa.device.brief_item import BriefItem
from quintessa.serde import to_dict

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime


def staleness(runtime: AgentRuntime, card: BriefItem) -> str:
    """Why a card may no longer hold, or "" when nothing changed under it."""
    store = runtime.store
    if card.topic_id:
        topic = store.topics.get(card.topic_id)
        if topic is None or topic.archived:
            return "its topic is gone"
        if topic.updated_at > card.updated_at:
            return "its topic changed after the card was written"
    if card.document_id:
        doc = store.documents.get(card.document_id)
        if doc is None or doc.status.value == "archived":
            return "its document is gone"
    return ""


def brief_context(runtime: AgentRuntime) -> dict[str, Any]:
    """What the brief shows now and which questions wait on the user, for the
    agent to read before it adds anything, highest salience first (expired
    cards are dropped first). A stashed question is one the user put aside
    for later; it still waits."""
    runtime.device.prune_brief(now())
    runtime.prune_stash()
    cards = [
        {
            "id": b.id,
            "text": b.text,
            "topic_id": b.topic_id,
            "document_id": b.document_id,
            "section_id": b.section_id,
            "urgency": b.urgency,
            "detail": b.detail,
            "action": b.action.label if b.action else None,
            "expires_at": b.expires_at,
            "due_at": b.due_at,
            "salience": b.salience,
            "updated_at": b.updated_at,
            "stale": staleness(runtime, b),
        }
        for b in runtime.device.state.brief
    ]
    questions = [
        {
            "id": r.id,
            "prompt": r.prompt,
            "topic_id": r.topic_id,
            "asked_at": r.created_at,
            "stashed": runtime.device.is_stashed(r.id),
        }
        for r in runtime.ux.pending.values()
    ]
    return to_dict({"brief": cards, "questions_waiting": questions})  # plain JSON, for Jev too
