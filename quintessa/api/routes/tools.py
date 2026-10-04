"""Adding, replacing and deleting the user's own tools."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from quintessa.api.bodies import ToolBody
from quintessa.api.deps import Agent
from quintessa.loop.runtime import AgentRuntime
from quintessa.models import Tool, ToolAuthor, ToolFunction, ToolKind, ToolParameter

router = APIRouter(prefix="/api")


@router.post("/tools")
async def put_tool(body: ToolBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
    existing = agent.store.tools.get(body.name)
    if body.kind == ToolKind.BUILTIN or (existing and existing.kind == ToolKind.BUILTIN):
        raise HTTPException(400, "built-in tools cannot be replaced")
    if body.kind == ToolKind.APP or (existing and existing.kind == ToolKind.APP):
        raise HTTPException(400, "apps are installed from the app store, not edited")
    agent.store.put_tool(
        Tool(
            name=body.name,
            description=body.description,
            kind=body.kind,
            grounding=body.grounding,
            endpoint=body.endpoint,
            code=body.code,
            created_by=ToolAuthor.USER,
            functions=[
                ToolFunction(
                    f.name,
                    f.description,
                    [ToolParameter(p.name, p.type, p.description, p.required) for p in f.parameters],
                    f.returns,
                    f.oversight,
                    f.long_running,
                )
                for f in body.functions
            ],
        )
    )
    return {"ok": True}


@router.delete("/tools/{name}")
async def delete_tool(name: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
    tool = agent.store.tools.get(name)
    if tool is None:
        raise HTTPException(404, "no such tool")
    if tool.kind == ToolKind.BUILTIN:
        raise HTTPException(400, "built-in tools cannot be deleted")
    agent.store.delete_tool(name)
    return {"ok": True}
