from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from quintessa.clock import now
from quintessa.executors import EXECUTORS, StepContext
from quintessa.executors.common import JSON_INSTRUCTION, session_context
from quintessa.llm import LLMUnavailableError
from quintessa.llm import schema as s
from quintessa.models import ReasoningSession, SessionStatus, StepDecision, TraceStep

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

log = logging.getLogger(__name__)

DONE = "done"


class AgentReasoningLoop:
    """Chain-of-thought control loop. Each step the model picks one capability
    (or decides the chain is done); the capability runs; its result joins the
    session context for the next decision. Every step is kept as a trace."""

    def __init__(self, runtime: "AgentRuntime", session: ReasoningSession):
        self.runtime = runtime
        self.session = session

    def _decision_schema(self) -> dict:
        return s.obj(
            {
                "capability": s.enum_of([*self.runtime.capabilities, DONE]),
                "focus": s.string("Exactly what the capability should do in this step."),
                "rationale": s.string(),
                "status_words": s.string("One or two words for the dynamic island."),
            }
        )

    async def decide(self) -> tuple[StepDecision, str, str]:
        ctx = {
            "capabilities": [
                {"name": c.name, "description": c.description} for c in self.runtime.capabilities.values()
            ],
            **session_context(self.session),
            "memory": self.runtime.store.snapshot(),
            "on_screen": self.runtime.on_screen(),
            "max_steps_left": self.runtime.max_steps - len(self.session.steps),
        }
        result = await self.runtime.llm.generate_json(
            system=f"{self.runtime.controller_prompt}\n\n{JSON_INSTRUCTION}",
            prompt=json.dumps(ctx, indent=1, default=str),
            schema=self._decision_schema(),
            purpose="decide",
        )
        d = result.data
        capability = "" if d["capability"] == DONE else d["capability"]
        return StepDecision(capability, d["focus"], d["rationale"]), d["status_words"], result.model

    async def run(self) -> ReasoningSession:
        runtime, session = self.runtime, self.session
        try:
            for index in range(runtime.max_steps):
                decision, words, model = await self.decide()
                if not decision.capability:
                    break
                runtime.device.session_activity(session.id, words)
                step = TraceStep(index, decision.capability, decision.focus, decision.rationale, model=model)
                session.steps.append(step)
                capability = runtime.capabilities[decision.capability]
                outcome = await EXECUTORS[capability.executor].run(StepContext(runtime, session, capability, decision))
                if outcome.pending_ux is not None and outcome.on_answer is not None:
                    step.output, step.summary = outcome.output, outcome.summary
                    outcome = await self._wait_for_user(outcome)
                step.output, step.summary, step.model = outcome.output, outcome.summary, outcome.model or model
                step.ended_at = now()
            else:
                log.info("session %s reached max steps", session.id)
            session.status = SessionStatus.COMPLETE
        except LLMUnavailableError as e:
            self._fail(f"LLM unavailable: {e}")
        except Exception as e:  # keep other loops alive; the trace shows what broke
            log.exception("session %s failed", session.id)
            self._fail(f"{type(e).__name__}: {e}")
        finally:
            session.ended_at = now()
            runtime.device.session_activity(session.id, None)
            runtime.store.put_session(session)
        return session

    async def _wait_for_user(self, outcome):
        runtime, session = self.runtime, self.session
        request = outcome.pending_ux
        session.status = SessionStatus.WAITING_FOR_USER
        session.pending_ux_id = request.id
        runtime.store.put_session(session)
        runtime.device.show_ux(request.id)
        runtime.device.session_activity(session.id, "Waiting for you")
        response = await runtime.ux.ask(request)
        runtime.device.close_ux(request.id, request.document_id, request.section_id)
        session.status = SessionStatus.RUNNING
        session.pending_ux_id = None
        runtime.store.put_session(session)
        return await outcome.on_answer(response)

    def _fail(self, message: str) -> None:
        self.session.status = SessionStatus.FAILED
        if self.session.steps and not self.session.steps[-1].ended_at:
            self.session.steps[-1].error = message
            self.session.steps[-1].ended_at = now()
        else:
            self.session.steps.append(TraceStep(len(self.session.steps), "", "", "", error=message, ended_at=now()))

