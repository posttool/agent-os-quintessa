from __future__ import annotations

import json
from typing import Any

from quintessa.context import JSON_INSTRUCTION, capability_context
from quintessa.executors.step_context import StepContext
from quintessa.llm.result import LLMResult


async def call_capability(
    ctx: StepContext, schema: dict[str, Any], extra: dict[str, Any] | None = None, *, stage: str = ""
) -> LLMResult:
    """One model call for the capability. `stage` names a later call of a
    multi-call capability in its purpose (capability:tool_discovery:choose)."""
    payload = {**capability_context(ctx.runtime, ctx.session, ctx.decision.focus), **(extra or {})}
    return await ctx.runtime.llm.generate_json(
        system=f"{ctx.capability.instructions}\n\n{JSON_INSTRUCTION}",
        prompt=json.dumps(payload, indent=1, default=str),
        schema=schema,
        purpose=f"capability:{ctx.capability.name}" + (f":{stage}" if stage else ""),
    )
