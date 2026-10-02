from __future__ import annotations

import json
from importlib import resources

from quintessa.executors.common import call_capability
from quintessa.executors.step_context import StepContext
from quintessa.executors.step_outcome import StepOutcome
from quintessa.llm import schema as s
from quintessa.models import OversightLevel, Tool, ToolFunction, ToolKind, ToolParameter

_KINDS = [k.value for k in ToolKind if k != ToolKind.BUILTIN]

SCHEMA = s.obj(
    {
        "reuse": s.array(s.string(), "Names of existing tools that already fit."),
        "tools": s.array(
            s.obj(
                {
                    "name": s.string(),
                    "description": s.string(),
                    "kind": s.enum_of(_KINDS),
                    "grounding": s.string("System prompt for llm tools; empty otherwise."),
                    "endpoint": s.string(),
                    "code": s.string(),
                    "functions": s.array(
                        s.obj(
                            {
                                "name": s.string(),
                                "description": s.string(),
                                "parameters": s.array(
                                    s.obj(
                                        {
                                            "name": s.string(),
                                            "type": s.string(),
                                            "description": s.string(),
                                            "required": s.boolean(),
                                        }
                                    )
                                ),
                                "returns": s.string(),
                                "oversight": s.enum_of(OversightLevel),
                                "long_running": s.boolean(),
                            }
                        )
                    ),
                }
            )
        ),
        "notes": s.string(),
    }
)


def tool_suggestions() -> list[dict]:
    return json.loads(resources.files("quintessa.samples").joinpath("tool_suggestions.json").read_text())


class ToolDiscoveryExecutor:
    async def run(self, ctx: StepContext) -> StepOutcome:
        result = await call_capability(ctx, SCHEMA, {"sample_tool_suggestions": tool_suggestions()})
        store = ctx.runtime.store
        added = []
        async with store.lock:
            for t in result.data["tools"]:
                if t["name"] in store.tools and store.tools[t["name"]].kind == ToolKind.BUILTIN:
                    continue
                store.put_tool(
                    Tool(
                        name=t["name"],
                        description=t["description"],
                        kind=ToolKind(t["kind"]),
                        grounding=t["grounding"],
                        endpoint=t["endpoint"],
                        code=t["code"],
                        functions=[
                            ToolFunction(
                                f["name"],
                                f["description"],
                                [ToolParameter(p["name"], p["type"], p["description"], p["required"]) for p in f["parameters"]],
                                f["returns"],
                                OversightLevel(f["oversight"]),
                                f["long_running"],
                            )
                            for f in t["functions"]
                        ],
                    )
                )
                added.append(t["name"])
        summary = f"Added tools {added}; reusing {result.data['reuse']}. {result.data['notes']}".strip()
        return StepOutcome(output={**result.data, "added": added}, summary=summary, model=result.model)
