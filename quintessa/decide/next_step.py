from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

from quintessa.decide.system_one import DEFAULT_MODEL, DEFAULT_URL, SystemOneClient, SystemOneError, choice
from quintessa.models import ReasoningSession, ShadowDecision
from quintessa.serde import to_dict

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

DONE = "done"
QUESTION = "next_step"
INSTRUCTIONS = (
    "A personal agent is working through what to do about the trigger, one step at a time. "
    "Given the trigger, the steps it has already taken and what it knows, which step should it take next? "
    "A step that already succeeded with the same purpose should not be repeated."
)
DONE_WHEN = (
    "Nothing useful remains for this trigger: the steps taken so far have handled it, or it needs nothing at all, "
    "as many ambient events do."
)


class NextStepDecider:
    """Asks a System One model which capability should run next, as a
    Choice over the capabilities and "done". Used in shadow mode: the LLM
    still decides, and this answer is recorded beside it."""

    def __init__(self, client: SystemOneClient):
        self.client = client

    @staticmethod
    def question(runtime: "AgentRuntime") -> dict[str, Any]:
        criteria = {c.name: c.choose_when or c.description for c in runtime.capabilities.values()}
        criteria[DONE] = DONE_WHEN
        return choice(INSTRUCTIONS, criteria)

    @staticmethod
    def state(runtime: "AgentRuntime", session: ReasoningSession) -> dict[str, Any]:
        """A trimmed view of what the LLM controller sees: no raw graph,
        just the trigger, the chain so far and the outline of memory."""
        trigger = session.trigger
        store = runtime.store
        return {
            "trigger": {"kind": trigger.kind.value, "content": trigger.content, "sender": trigger.sender, "source": trigger.source},
            "steps_so_far": [
                {"capability": s.capability, "focus": s.focus, "summary": s.summary, "error": s.error}
                for s in session.steps
                if s.ended_at is not None
            ],
            "session_permissions": [to_dict(p) for p in session.permissions],
            "topics": [
                {"title": t.title, "summary": t.summary, "progress": t.progress}
                for t in store.topics.values()
                if not t.archived
            ],
            "documents": [d.title for d in store.documents.values() if d.status.value != "archived"],
            "tools": sorted(store.tools),
            "on_screen": _on_screen(runtime),
            "max_steps_left": runtime.max_steps - len(session.steps),
        }

    async def shadow(self, runtime: "AgentRuntime", session: ReasoningSession) -> ShadowDecision:
        """Never raises: a failed call is recorded with its error."""
        decision = ShadowDecision(step_index=len(session.steps), llm_choice="", model=self.client.label)
        started = time.perf_counter()
        try:
            answers, model = await self.client.ask(self.state(runtime, session), {QUESTION: self.question(runtime)})
            answer = answers[QUESTION]
            decision.choice = answer["choice"]
            decision.probabilities = {k: float(v) for k, v in answer.get("probabilities", {}).items()}
            decision.confidence = float(answer.get("confidence", 0.0))
            decision.model = model
        except (SystemOneError, KeyError, TypeError, ValueError) as e:
            decision.error = str(e) or type(e).__name__
        decision.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return decision


def _on_screen(runtime: "AgentRuntime") -> dict[str, Any] | None:
    view = runtime.on_screen()
    doc = view and runtime.store.documents.get(view["document_id"])
    if not doc:
        return None
    sections = [doc.section(sid) for sid in view["section_ids"]]
    return {"document": doc.title, "mode": view["mode"], "sections": [s.title for s in sections if s is not None]}


def shadow_decider_from_env() -> NextStepDecider | None:
    """Shadow mode is on when a Jev key is configured, unless
    QUINTESSA_DECIDER=llm turns it off.

    Environment:
      QUINTESSA_JEV_API_KEY   key for the System One endpoint (TYPESAFE_API_KEY also works)
      QUINTESSA_JEV_URL       endpoint base URL (default TypeSafe's; a gev URL works too)
      QUINTESSA_JEV_MODEL     model name (default jev-latest)
      QUINTESSA_DECIDER       "llm" to turn shadow mode off
    """
    if os.environ.get("QUINTESSA_DECIDER", "shadow") == "llm":
        return None
    key = os.environ.get("QUINTESSA_JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY")
    if not key:
        return None
    return NextStepDecider(
        SystemOneClient(
            key,
            base_url=os.environ.get("QUINTESSA_JEV_URL", DEFAULT_URL),
            model=os.environ.get("QUINTESSA_JEV_MODEL", DEFAULT_MODEL),
        )
    )
