"""What the models read: the context handed to the controller, to each
capability, and to Jev, assembled from memory, the device and the session.
Keeping it in one place means the LLM and Jev decide on the same facts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from quintessa.clock import now
from quintessa.device import Card
from quintessa.models import ReasoningSession
from quintessa.serde import to_dict

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime
    from quintessa.memory import MemoryStore

JSON_INSTRUCTION = "Respond only with a JSON object that matches the provided schema."


def session_context(session: ReasoningSession) -> dict[str, Any]:
    return {
        "now": now().isoformat(),
        "trigger": to_dict(session.trigger),
        "steps_so_far": [
            {"capability": s.capability, "focus": s.focus, "summary": s.summary, "error": s.error}
            for s in session.steps
            if s.ended_at is not None  # the step being run now is described by `focus`
        ],
        "session_permissions": [to_dict(p) for p in session.permissions],
    }


def controller_context(runtime: AgentRuntime, session: ReasoningSession) -> dict[str, Any]:
    """Everything the next-step decision is made from. The LLM controller
    and Jev's next_step question both read this, so they decide on the same
    facts."""
    return {
        "capabilities": [{"name": c.name, "description": c.description} for c in runtime.capabilities.values()],
        **session_context(session),
        "memory": runtime.store.snapshot(),
        "on_screen": runtime.on_screen(),
        **brief_context(runtime),
        "max_steps_left": runtime.max_steps - len(session.steps),
    }


def capability_context(runtime: AgentRuntime, session: ReasoningSession, focus: str) -> dict[str, Any]:
    """What one capability step reads: its focus, the session so far, memory,
    the screen and the brief."""
    return {
        "focus": focus,
        **session_context(session),
        "memory": runtime.store.snapshot(),
        "on_screen": runtime.on_screen(),
        **brief_context(runtime),
    }


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
            "stale": staleness(runtime.store, b),
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
        for r in runtime.questions.pending.values()
    ]
    return to_dict({"brief": cards, "questions_waiting": questions})  # plain JSON, for Jev too


def staleness(store: MemoryStore, card: Card) -> str:
    """Why a card may no longer hold, or "" when nothing changed under it."""
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
