from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx

from quintessa.llm import schema as s
from quintessa.models import AuthState, Tool, ToolBinding, ToolFunction, ToolKind
from quintessa.serde import to_dict
from quintessa.tools.builtin import BUILTIN_IMPLEMENTATIONS, FETCH_LIMIT
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


async def run_tool(runtime: "AgentRuntime", tool: Tool, function: ToolFunction, args: dict[str, str]) -> ToolCallResult:
    """Execute one function call. Builtins run in code, web API tools make a
    real HTTP request, and the rest are a differently grounded model acting
    as the service. A network failure is a failed call, not a failed session."""
    try:
        if tool.kind == ToolKind.BUILTIN:
            impl = BUILTIN_IMPLEMENTATIONS.get((tool.name, function.name))
            if impl is None:
                return ToolCallResult("failed", f"{tool.name}.{function.name} has no implementation")
            return await impl(args, runtime)
        if tool.kind == ToolKind.APP:
            return await _call_app(runtime, tool, function, args)
        if tool.kind == ToolKind.WEB_API:
            return await _call_web_api(runtime, tool, function, args)
        if tool.kind in SIMULATED_KINDS:
            return await _simulate(runtime, tool, function, args)
    except httpx.HTTPError as e:
        return ToolCallResult("failed", f"{tool.name}.{function.name}: {type(e).__name__}: {e}")
    return ToolCallResult("failed", f"running {tool.kind.value} tools is not implemented yet")


async def _call_app(runtime: "AgentRuntime", tool: Tool, function: ToolFunction, args: dict[str, str]) -> ToolCallResult:
    """Installed apps run through their binding. Only simulated apps exist
    today; a real binding would first need the user signed in."""
    title = tool.listing.title if tool.listing else tool.name
    if tool.auth.state == AuthState.NEEDED:
        return ToolCallResult("needs_user", f"Sign in to {title} before the agent can use it.")
    if tool.binding == ToolBinding.SIMULATED:
        return await _simulate(runtime, tool, function, args)
    return ToolCallResult("failed", f"{title}: running apps through {tool.binding.value} is not implemented yet")


async def _simulate(runtime: "AgentRuntime", tool: Tool, function: ToolFunction, args: dict[str, str]) -> ToolCallResult:
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


async def _call_web_api(runtime: "AgentRuntime", tool: Tool, function: ToolFunction, args: dict[str, str]) -> ToolCallResult:
    """The model turns the call into an HTTP request against the tool's
    endpoint; the request itself is made here and its response reported."""
    plan = await runtime.llm.generate_json(
        system=(
            f"You turn function calls for the web API '{tool.name}' ({tool.description}) into HTTP requests. "
            f"Base endpoint: {tool.endpoint or 'unknown; use the public API you know for this service'}."
            + (f"\nNotes: {tool.grounding}" if tool.grounding else "")
        ),
        prompt=json.dumps({"function": to_dict(function), "arguments": args}, indent=2),
        schema=WEB_API_REQUEST_SCHEMA,
        purpose=f"tool:{tool.name}.{function.name}:request",
    )
    req = plan.data
    url = httpx.URL(req["url"])
    if url.scheme not in ("http", "https"):
        return ToolCallResult("failed", f"{tool.name}.{function.name}: refusing non-http URL {req['url']}")
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        response = await client.request(
            req["method"], url, headers={h["name"]: h["value"] for h in req["headers"]},
            content=req["body"].encode() if req["body"] else None,
        )
    text = response.text
    note = f"\n[truncated to {FETCH_LIMIT} of {len(text)} characters]" if len(text) > FETCH_LIMIT else ""
    status = "done" if response.is_success else "failed"
    return ToolCallResult(status, f"{req['method']} {url} -> HTTP {response.status_code}\n{text[:FETCH_LIMIT]}{note}")
