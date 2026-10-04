"""Simulated ambient data: sources of texts, emails, locations and the like,
written by hand, from a template or from a description."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from quintessa.ambient import ambient_templates, source_from_description, source_from_template
from quintessa.api.bodies import EnabledBody, SourceBody, SourcePatch, TemplateSourceBody, VibeSourceBody
from quintessa.api.deps import Agent
from quintessa.llm import LLMError
from quintessa.loop.runtime import AgentRuntime
from quintessa.models import AmbientSource

router = APIRouter(prefix="/api")


@router.get("/ambient/templates")
async def templates() -> list[dict[str, Any]]:
    return ambient_templates()


@router.put("/ambient/enabled")
async def set_enabled(body: EnabledBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
    agent.ambient.set_enabled(body.enabled)
    return {"ok": True}


@router.post("/ambient/sources")
async def add_source(body: SourceBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
    source = AmbientSource(
        body.name,
        body.kind,
        body.events,
        body.interval_seconds,
        device=body.device,
        sender=body.sender,
        loop=body.loop,
    )
    agent.ambient.add_source(source)
    return {"id": source.id}


@router.post("/ambient/sources/from-template")
async def add_from_template(body: TemplateSourceBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
    template = next((t for t in ambient_templates() if t["name"] == body.template), None)
    if template is None:
        raise HTTPException(404, "no such template")
    try:
        source = await source_from_template(agent.llm, template, _persona_profile(agent), body.count)
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    agent.ambient.add_source(source)
    return {"id": source.id}


@router.post("/ambient/sources/vibe")
async def add_vibe(body: VibeSourceBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
    try:
        source = await source_from_description(agent.llm, body.description, _persona_profile(agent), body.count)
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    agent.ambient.add_source(source)
    return {"id": source.id}


@router.patch("/ambient/sources/{source_id}")
async def patch_source(source_id: str, body: SourcePatch, agent: AgentRuntime = Agent) -> dict[str, Any]:
    source = agent.ambient.sources.get(source_id)
    if source is None:
        raise HTTPException(404, "no such source")
    if body.speed is not None:
        agent.ambient.set_speed(source_id, max(body.speed, 0.01))
    if body.enabled is not None:
        source.enabled = body.enabled
        agent.notify_changed()
    return {"ok": True}


@router.delete("/ambient/sources/{source_id}")
async def delete_source(source_id: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
    agent.ambient.remove_source(source_id)
    return {"ok": True}


def _persona_profile(agent: AgentRuntime) -> dict[str, Any] | None:
    return None if agent.persona is None else agent.persona["profile"]
