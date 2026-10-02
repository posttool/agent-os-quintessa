from __future__ import annotations

import json
from typing import Any

from quintessa.clock import now
from quintessa.executors.step_context import StepContext
from quintessa.llm.result import LLMResult
from quintessa.models import ReasoningSession
from quintessa.serde import to_dict

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


async def call_capability(ctx: StepContext, schema: dict[str, Any], extra: dict[str, Any] | None = None) -> LLMResult:
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
        purpose=f"capability:{ctx.capability.name}",
    )
