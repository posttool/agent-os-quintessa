from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING

import httpx

from quintessa import config
from quintessa.llm import schema as s
from quintessa.models import AuthState, Tool, ToolBinding, ToolCallRecord, ToolCallStatus, ToolFunction, ToolKind
from quintessa.prompts import prompt
from quintessa.serde import to_dict
from quintessa.tools.builtin import BUILTIN_IMPLEMENTATIONS, clip
from quintessa.tools.tool_call_result import ToolCallResult

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

LLM_TOOL_SCHEMA = s.obj(
    {
        "status": s.enum_of(ToolCallStatus),
        "result": s.string("What happened, as the tool would report it."),
        "progress_stages": s.array(s.string(), "Stages still to come if the process continues."),
    }
)


WEB_API_REQUEST_SCHEMA = s.obj(
    {
        "method": s.enum_of(["GET", "POST", "PUT", "PATCH", "DELETE"]),
        "url": s.string("Full https URL, including any query string."),
        "headers": s.array(s.obj({"name": s.string(), "value": s.string()})),
        "body": s.nullable(s.string("JSON request body, or null.")),
    }
)

# MCP and agent-written code tools have no runtime yet; until they do, a
# model grounded in the tool's description plays the service, like llm tools.
SIMULATED_KINDS = (ToolKind.LLM, ToolKind.MCP, ToolKind.CODE)

# A simulated tool keeps its recent calls and sees them on each new call,
# so a menu, an order or a booking matches what it reported earlier.
DEFAULT_FAILURE_RATE = 0.2  # about one simulated call in five runs into a problem
HISTORY_KEPT = 30
HISTORY_SHOWN = 12
HISTORY_RESULT_LIMIT = 3000
SUCCEED_INSTRUCTION = prompt("simulated_tool_succeed")
FAIL_INSTRUCTION = prompt("simulated_tool_fail")


def failure_rate() -> float:
    """How often a simulated call runs into a problem, from
    QUINTESSA_SIM_FAILURE_RATE (default 0.2: about one call in five)."""
    return config.sim_failure_rate(DEFAULT_FAILURE_RATE)


def _schema(statuses: list[str]) -> dict:
    return s.obj({**LLM_TOOL_SCHEMA["properties"], "status": s.enum_of(statuses)})


SUCCEED_SCHEMA = _schema([ToolCallStatus.DONE, ToolCallStatus.IN_PROGRESS])
FAIL_SCHEMA = _schema([ToolCallStatus.FAILED, ToolCallStatus.NEEDS_USER])
_rng = random.Random()


async def run_tool(
    runtime: AgentRuntime, tool: Tool, function: ToolFunction, args: dict[str, str], *, purpose: str = ""
) -> ToolCallResult:
    """Execute one function call. Builtins run in code, web API tools make a
    real HTTP request, and the rest are a differently grounded model acting
    as the service. A network failure is a failed call, not a failed session."""
    try:
        if tool.kind == ToolKind.BUILTIN:
            impl = BUILTIN_IMPLEMENTATIONS.get((tool.name, function.name))
            if impl is None:
                return ToolCallResult(ToolCallStatus.FAILED, f"{tool.name}.{function.name} has no implementation")
            return await impl(args, runtime)
        if tool.kind == ToolKind.APP:
            return await _call_app(runtime, tool, function, args, purpose)
        if tool.kind == ToolKind.WEB_API:
            return await _call_web_api(runtime, tool, function, args)
        if tool.kind in SIMULATED_KINDS:
            return await _simulate(runtime, tool, function, args, purpose)
    except httpx.HTTPError as e:
        return ToolCallResult(ToolCallStatus.FAILED, f"{tool.name}.{function.name}: {type(e).__name__}: {e}")
    return ToolCallResult(ToolCallStatus.FAILED, f"running {tool.kind.value} tools is not implemented yet")


async def _call_app(
    runtime: AgentRuntime, tool: Tool, function: ToolFunction, args: dict[str, str], purpose: str
) -> ToolCallResult:
    """Installed apps run through their binding. Only simulated apps exist
    today; a real binding would first need the user signed in."""
    title = tool.listing.title if tool.listing else tool.name
    if tool.auth.state == AuthState.NEEDED:
        return ToolCallResult(ToolCallStatus.NEEDS_USER, f"Sign in to {title} before the agent can use it.")
    if tool.binding == ToolBinding.SIMULATED:
        return await _simulate(runtime, tool, function, args, purpose)
    return ToolCallResult(
        ToolCallStatus.FAILED, f"{title}: running apps through {tool.binding.value} is not implemented yet"
    )


async def _simulate(
    runtime: AgentRuntime, tool: Tool, function: ToolFunction, args: dict[str, str], purpose: str
) -> ToolCallResult:
    earlier = [
        {"function": r.function, "arguments": r.arguments, "status": r.status, "result": r.result}
        for r in tool.history[-HISTORY_SHOWN:]
    ]
    # The outcome is drawn here rather than left to the model, which on its
    # own refused most calls (strict argument checks, asking for approval the
    # agent had already got). The oversight level is left out for the same reason.
    fails = _rng.random() < failure_rate()
    described = {k: v for k, v in to_dict(function).items() if k != "oversight"}
    result = await runtime.llm.generate_json(
        system=tool.grounding or prompt("simulated_tool_default", name=tool.name, description=tool.description),
        prompt=json.dumps(
            {
                "function": described,
                "arguments": args,
                "why_the_agent_is_calling": purpose,
                "earlier_calls": earlier,
                "instruction": FAIL_INSTRUCTION if fails else SUCCEED_INSTRUCTION,
            },
            indent=2,
        ),
        schema=FAIL_SCHEMA if fails else SUCCEED_SCHEMA,
        purpose=f"tool:{tool.name}.{function.name}",
    )
    data = result.data
    _remember(
        runtime,
        tool,
        ToolCallRecord(function.name, args, purpose, data["status"], data["result"][:HISTORY_RESULT_LIMIT]),
    )
    return ToolCallResult(data["status"], data["result"], data["progress_stages"])


def _remember(runtime: AgentRuntime, tool: Tool, record: ToolCallRecord) -> None:
    tool.history = [*tool.history, record][-HISTORY_KEPT:]
    if runtime.store.tools.get(tool.name) is tool:  # not if it was uninstalled meanwhile
        runtime.store.put_tool(tool)


async def _call_web_api(
    runtime: AgentRuntime, tool: Tool, function: ToolFunction, args: dict[str, str]
) -> ToolCallResult:
    """The model turns the call into an HTTP request against the tool's
    endpoint; the request itself is made here and its response reported."""
    plan = await runtime.llm.generate_json(
        system=prompt(
            "web_api_request",
            name=tool.name,
            description=tool.description,
            endpoint=tool.endpoint or "unknown; use the public API you know for this service",
            notes=f"\nNotes: {tool.grounding}" if tool.grounding else "",
        ),
        prompt=json.dumps({"function": to_dict(function), "arguments": args}, indent=2),
        schema=WEB_API_REQUEST_SCHEMA,
        purpose=f"tool:{tool.name}.{function.name}:request",
    )
    req = plan.data
    url = httpx.URL(req["url"])
    if url.scheme not in ("http", "https"):
        return ToolCallResult(ToolCallStatus.FAILED, f"{tool.name}.{function.name}: refusing non-http URL {req['url']}")
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        response = await client.request(
            req["method"],
            url,
            headers={h["name"]: h["value"] for h in req["headers"]},
            content=req["body"].encode() if req["body"] else None,
        )
    status = ToolCallStatus.DONE if response.is_success else ToolCallStatus.FAILED
    return ToolCallResult(status, f"{req['method']} {url} -> HTTP {response.status_code}\n{clip(response.text)}")
