"""Scores brief cards with a System One model (Jev, gev): urgency, contextual
relevance and sender/entity affinity, as three score questions with
rubrics from the salience dimensions (see quintessa/device/salience.py).
Typed scores with probabilities are what Jev is built for, it answers in
well under a second, and cards can be scored side by side."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from quintessa.clock import now
from quintessa.decide.system_one import SystemOneClient, SystemOneError
from quintessa.device import BriefItem
from quintessa.models import InputKind

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

QUESTIONS: dict[str, dict[str, Any]] = {
    "urgency": {
        "type": "score",
        "instructions": "How much personal risk does the user take on if they do not act on this card?",
        "criteria": [
            "Ambient or routine: a daily brief, an FYI, a screen time or health report.",
            "Good to know soon, but nothing is lost by waiting.",
            "A perishable window: rain starting where they are in minutes, a 2FA code, a missed important call, a subscription about to lapse.",
            "A hard commitment today: a meeting, a flight, a delivery, a paid event, a visit from a tradesperson.",
            "A hard commitment happening now: a meeting starting in minutes, boarding has begun, the courier is outside.",
        ],
    },
    "relevance": {
        "type": "score",
        "instructions": (
            "How well does this card fit the user's context right now: where they are, the time of day, "
            "and what they have just been doing?"
        ),
        "criteria": [
            "Out of place now: about another place or time of day, or they are asleep or busy with something else.",
            "Could matter now, but nothing in their context points to it.",
            "Fits their context: the right place or time of day for it.",
            "Exactly what their context calls for right now.",
        ],
    },
    "affinity": {
        "type": "score",
        "instructions": "How much does the person or business this card is about matter to the user?",
        "criteria": [
            "A stranger, a brand or an automated sender.",
            "An acquaintance or a service they use now and then.",
            "Someone they deal with often: a colleague, a friend, a regular service.",
            "Their closest people: partner, family, close friends, their manager.",
        ],
    },
}


def normalized(answer: dict[str, Any], levels: int) -> float:
    return min(max(float(answer["score"]) / (levels - 1), 0.0), 1.0)


class BriefRanker:
    def __init__(self, client: SystemOneClient):
        self.client = client

    @staticmethod
    def state(runtime: "AgentRuntime", card: BriefItem) -> dict[str, Any]:
        """The card, its topic, and the user's context: the time, where they
        last were, and the latest things that happened."""
        store = runtime.store
        topic = store.topics.get(card.topic_id) if card.topic_id else None
        events = store.events[-8:]
        location = next((e for e in reversed(store.events) if e.kind == InputKind.LOCATION), None)
        return {
            "now": now().isoformat(),
            "card": {"text": card.text, "detail": card.detail, "due_at": card.due_at.isoformat() if card.due_at else None},
            "topic": {"title": topic.title, "summary": topic.summary, "due": topic.due} if topic else None,
            "context": {
                "last_location": location.content if location else None,
                "recent": [{"kind": e.kind.value, "sender": e.sender, "content": e.content[:200]} for e in events],
            },
            "people": [n.title for n in store.nodes.values() if n.type.value == "person"],
        }

    async def score(self, runtime: "AgentRuntime", cards: list[BriefItem]) -> list[str]:
        """Score the cards side by side and write the scores onto them.
        Never raises; returns one line per card for the trace."""
        started = time.perf_counter()

        async def one(card: BriefItem) -> str:
            try:
                answers, model = await self.client.ask(self.state(runtime, card), QUESTIONS)
                s = card.salience
                s.urgency = normalized(answers["urgency"], len(QUESTIONS["urgency"]["criteria"]))
                s.relevance = normalized(answers["relevance"], len(QUESTIONS["relevance"]["criteria"]))
                s.affinity = normalized(answers["affinity"], len(QUESTIONS["affinity"]["criteria"]))
                s.scored_by, s.scored_at = model, card.updated_at
                return f"{card.text}: urgency {s.urgency:.2f}, fits now {s.relevance:.2f}, person {s.affinity:.2f}"
            except (SystemOneError, KeyError, TypeError, ValueError) as e:
                return f"{card.text}: kept the agent's scores ({str(e) or type(e).__name__})"

        lines = await asyncio.gather(*(one(c) for c in cards))
        ms = round((time.perf_counter() - started) * 1000)
        return [*lines, f"{len(cards)} cards in {ms} ms"]
