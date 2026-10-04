"""Aura personas: listing them, and replaying one person's day into an agent."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from quintessa.api.bodies import PersonaStartBody
from quintessa.api.deps import Agent, Api, ApiState
from quintessa.loop.runtime import AgentRuntime
from quintessa.persona import PersonaSimulation
from quintessa.serde import to_dict

router = APIRouter(prefix="/api")


@router.get("/personas")
async def list_personas(api: ApiState = Api) -> list[dict[str, Any]]:
    try:
        people = await api.personas_client().list_personas()
    except Exception as e:  # network or service errors surface to the picker
        raise HTTPException(502, f"could not reach the Aura persona service: {e}") from e
    return [to_dict(p.summary()) for p in people]


@router.post("/persona/start")
async def start_persona(body: PersonaStartBody, agent: AgentRuntime = Agent, api: ApiState = Api) -> dict[str, Any]:
    await api.stop_persona(agent.user_id)
    sim = PersonaSimulation(agent, api.personas_client(), speed=body.speed)
    try:
        profile = await sim.start(body.persona_id, body.date)
    except Exception as e:
        raise HTTPException(502, f"could not start the persona: {e}") from e
    api.personas[agent.user_id] = sim
    agent.attach_persona(body.persona_id, sim.date, profile)
    return {"ok": True, "date": sim.date}


@router.post("/persona/stop")
async def stop_persona(agent: AgentRuntime = Agent, api: ApiState = Api) -> dict[str, Any]:
    entry = api.personas.get(agent.user_id)
    if entry:
        await entry.stop()
        agent.notify_changed()
    return {"ok": True}
