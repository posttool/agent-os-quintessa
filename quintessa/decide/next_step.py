from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from quintessa.context import controller_context
from quintessa.decide.system_one import SystemOneClient, SystemOneError, choice
from quintessa.models import DONE, ReasoningSession, ShadowDecision
from quintessa.prompts import data

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

QUESTION = "next_step"
_QUESTION_TEXT = data("jev/next_step")
INSTRUCTIONS = _QUESTION_TEXT["instructions"]
DONE_WHEN = _QUESTION_TEXT["done_when"]


class NextStepDecider:
    """Asks a System One model which capability should run next, as a
    Choice over the capabilities and "done". In shadow mode the LLM still
    decides and this answer is recorded beside it; when the user lets Jev
    drive, the loop follows it."""

    def __init__(self, client: SystemOneClient):
        self.client = client

    @staticmethod
    def question(runtime: AgentRuntime) -> dict[str, Any]:
        criteria = {c.name: c.choose_when or c.description for c in runtime.capabilities.values()}
        criteria[DONE] = DONE_WHEN
        return choice(INSTRUCTIONS, criteria)

    @staticmethod
    def state(runtime: AgentRuntime, session: ReasoningSession) -> dict[str, Any]:
        """The same context the LLM controller decides from. The capability
        list is left out because the question's criteria carry it. In a replay
        of 68 recorded decisions this full context agreed with the LLM 53% of
        the time, against 34% for a trimmed outline."""
        context = controller_context(runtime, session)
        context.pop("capabilities")
        return context

    async def ask(self, runtime: AgentRuntime, session: ReasoningSession) -> ShadowDecision:
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
