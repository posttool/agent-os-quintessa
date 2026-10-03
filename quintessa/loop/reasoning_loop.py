from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from quintessa.clock import now
from quintessa.decide import is_ambient
from quintessa.executors import EXECUTORS, StepContext
from quintessa.executors.common import JSON_INSTRUCTION, controller_context
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

    async def decide(self) -> tuple[StepDecision, str, str, str]:
        """The next step, the island's status words, the model that chose
        and who decided ("jev" or "" for the LLM)."""
        driver = self.runtime.driver
        if driver is not None:
            record = await driver.shadow(self.runtime, self.session)
            if not record.error and record.choice in (*self.runtime.capabilities, DONE):
                record.drove = True
                self.session.shadow_decisions.append(record)
                capability = "" if record.choice == DONE else record.choice
                p = record.probabilities.get(record.choice, 0.0)
                focus = "Chosen by Jev with no instructions: decide what this capability should do for the trigger, given the steps so far."
                words = capability.replace("_", " ").title()
                return StepDecision(capability, focus, f"Jev p {p:.2f}"), words, record.model, "jev"
            # Jev failed: the LLM decides this step, and the failure stays on the record
            result = await self._ask_llm()
            record.llm_choice = result.data["capability"]
            self.session.shadow_decisions.append(record)
            return (*self._from_llm(result), "")
        result = await self._ask_llm()
        return (*self._from_llm(result), "")

    def _from_llm(self, result) -> tuple[StepDecision, str, str]:
        d = result.data
        capability = "" if d["capability"] == DONE else d["capability"]
        return StepDecision(capability, d["focus"], d["rationale"]), d["status_words"], result.model

    async def _ask_llm(self):
        ctx = controller_context(self.runtime, self.session)
        llm_call = self.runtime.llm.generate_json(
            system=f"{self.runtime.controller_prompt}\n\n{JSON_INSTRUCTION}",
            prompt=json.dumps(ctx, indent=1, default=str),
            schema=self._decision_schema(),
            purpose="decide",
        )
        shadow = self.runtime.shadow
        if shadow is None or self.runtime.driver is not None:
            return await llm_call
        # asked alongside the LLM (it is usually much faster); recorded, never followed
        result, record = await asyncio.gather(llm_call, shadow.shadow(self.runtime, self.session))
        record.llm_choice = result.data["capability"]
        self.session.shadow_decisions.append(record)
        return result

    async def run(self) -> ReasoningSession:
        runtime, session = self.runtime, self.session
        try:
            if runtime.ambient_filter is not None and is_ambient(session.trigger):
                session.prefilter = await runtime.ambient_filter.check(runtime, session.trigger)
                if session.prefilter.skipped:  # nothing worth a step; no LLM call is made
                    session.status = SessionStatus.COMPLETE
                    return session
            for index in range(runtime.max_steps):
                decision, words, model, decided_by = await self.decide()
                if not decision.capability:
                    break
                runtime.device.session_activity(session.id, words)
                step = TraceStep(index, decision.capability, decision.focus, decision.rationale, model=model, decided_by=decided_by)
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

