from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from quintessa.clock import now
from quintessa.executors.step_context import StepContext
from quintessa.llm.result import LLMResult
from quintessa.models import ReasoningSession
from quintessa.serde import to_dict

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

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


def controller_context(runtime: "AgentRuntime", session: ReasoningSession) -> dict[str, Any]:
    """Everything the next-step decision is made from. The LLM controller
    and Jev's next_step question both read this, so they decide on the same
    facts."""
    return {
        "capabilities": [{"name": c.name, "description": c.description} for c in runtime.capabilities.values()],
        **session_context(session),
        "memory": runtime.store.snapshot(),
        "on_screen": runtime.on_screen(),
        "max_steps_left": runtime.max_steps - len(session.steps),
    }


async def call_capability(
    ctx: StepContext, schema: dict[str, Any], extra: dict[str, Any] | None = None, *, stage: str = ""
) -> LLMResult:
    """One model call for the capability. `stage` names a later call of a
    multi-call capability in its purpose (capability:tool_discovery:choose)."""
    payload = {
        "focus": ctx.decision.focus,
        **session_context(ctx.session),
        "memory": ctx.runtime.store.snapshot(),
        "on_screen": ctx.runtime.on_screen(),
        **(extra or {}),
    }
    return await ctx.runtime.llm.generate_json(
        system=f"{ctx.capability.instructions}\n\n{JSON_INSTRUCTION}",
        prompt=json.dumps(payload, indent=1, default=str),
        schema=schema,
        purpose=f"capability:{ctx.capability.name}" + (f":{stage}" if stage else ""),
    )
