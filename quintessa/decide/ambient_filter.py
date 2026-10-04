from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

from quintessa.decide.card_scorer import CardScorer
from quintessa.decide.next_step import NextStepDecider
from quintessa.decide.system_one import SystemOneClient, SystemOneError, client_from_env
from quintessa.models import AmbientFilterDecision, InputEvent

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

QUESTION = "matters"
DEFAULT_THRESHOLD = 0.3  # on 60 hand-labeled events it missed nothing that mattered and skipped half the sessions
NOUL = {
    "type": "noul",
    "instructions": (
        "This incoming event matters to the user's personal agent: it brings new information, a request, a risk "
        "or a change that the agent should record or act on, given what the agent is already tracking."
    ),
    "criteria": {
        "true": "New facts, requests, changes or risks, especially about something being tracked.",
        "false": "Marketing, routine notices, small talk with nothing new, or ordinary movement and motion.",
    },
}


def is_ambient(event: InputEvent) -> bool:
    """Events nobody asked for: ambient sources and persona replays. What the
    user says and progress on processes the agent started always run."""
    return event.source.startswith("ambient:") or event.source == "persona"


class AmbientFilter:
    """Asks a System One model (Jev, gev) whether an ambient event matters
    before the reasoning loop spends any LLM calls on it."""

    def __init__(self, client: SystemOneClient, threshold: float = DEFAULT_THRESHOLD):
        self.client = client
        self.threshold = threshold

    @staticmethod
    def state(runtime: AgentRuntime, event: InputEvent) -> dict[str, Any]:
        """The event, and the outline of what the agent is tracking; without
        the outline the model cannot tell a delayed flight it is waiting on
        from any other notice."""
        store = runtime.store
        return {
            "event": {"kind": event.kind.value, "sender": event.sender, "content": event.content},
            "tracking": [{"topic": t.title, "summary": t.summary} for t in store.topics.values() if not t.archived],
            "documents": [
                {"title": d.title, "sections": [s.title for s in d.sections]}
                for d in store.documents.values()
                if d.status.value != "archived"
            ],
            "people": [n.title for n in store.nodes.values() if n.type.value == "person"],
        }

    async def check(self, runtime: AgentRuntime, event: InputEvent) -> AmbientFilterDecision:
        """Never raises; a failed call keeps the event."""
        decision = AmbientFilterDecision(matters=1.0, threshold=self.threshold, skipped=False, model=self.client.label)
        started = time.perf_counter()
        try:
            answers, model = await self.client.ask(self.state(runtime, event), {QUESTION: NOUL})
            decision.matters = float(answers[QUESTION]["noul"])
            decision.model = model
            decision.skipped = decision.matters < self.threshold
        except (SystemOneError, KeyError, TypeError, ValueError) as e:
            decision.error = str(e) or type(e).__name__
        decision.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return decision


def jev_options_from_env() -> dict[str, Any]:
    """AgentRuntime options for Jev that each user can switch on or off.
    Both deciders exist whenever a key is configured; QUINTESSA_DECIDER=llm
    and QUINTESSA_AMBIENT_FILTER=1 only set what users start with."""
    client = client_from_env()
    if client is None:
        return {}
    return {
        "jev_next_step": NextStepDecider(client),
        "jev_ambient_filter": AmbientFilter(client, _threshold()),
        "jev_card_scorer": CardScorer(client),
        "jev_shadow_default": os.environ.get("QUINTESSA_DECIDER", "shadow") != "llm",
        "jev_filter_default": os.environ.get("QUINTESSA_AMBIENT_FILTER") == "1",
    }


def _threshold() -> float:
    return float(os.environ.get("QUINTESSA_AMBIENT_THRESHOLD", DEFAULT_THRESHOLD))
