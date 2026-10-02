from __future__ import annotations

import json
from typing import TYPE_CHECKING

from quintessa.llm import schema as s
from quintessa.models import Tool, ToolFunction, ToolKind
from quintessa.serde import to_dict
from quintessa.tools.builtin import BUILTIN_IMPLEMENTATIONS
from quintessa.tools.tool_call_result import ToolCallResult

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

LLM_TOOL_SCHEMA = s.obj(
    {
        "status": s.enum_of(["done", "in_progress", "needs_user", "failed"]),
        "result": s.string("What happened, as the tool would report it."),
        "progress_stages": s.array(s.string(), "Stages still to come if the process continues."),
    }
)


async def run_tool(runtime: "AgentRuntime", tool: Tool, function: ToolFunction, args: dict[str, str]) -> ToolCallResult:
    """Execute one function call. Builtins run in code; LLM tools are a
    differently grounded model acting as the service."""
    if tool.kind == ToolKind.BUILTIN:
        impl = BUILTIN_IMPLEMENTATIONS.get((tool.name, function.name))
        if impl is None:
            return ToolCallResult("failed", f"{tool.name}.{function.name} has no implementation")
        return await impl(args, runtime)
    if tool.kind == ToolKind.LLM:
        result = await runtime.llm.generate_json(
            system=tool.grounding or f"You act as the service '{tool.name}': {tool.description}",
            prompt=json.dumps(
                {"function": to_dict(function), "arguments": args, "instruction": "Carry out this call and report."},
                indent=2,
            ),
            schema=LLM_TOOL_SCHEMA,
            purpose=f"tool:{tool.name}.{function.name}",
        )
        data = result.data
        return ToolCallResult(data["status"], data["result"], data["progress_stages"])
    return ToolCallResult("failed", f"running {tool.kind.value} tools is not implemented yet")
