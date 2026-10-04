"""What every route shares: the platform's state and the user's agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, Query, Request

from quintessa.api.model_settings import ModelSettings
from quintessa.host import AgentHost
from quintessa.llm import ResilientLLM
from quintessa.loop.runtime import AgentRuntime
from quintessa.persona import AuraPersonaClient, PersonaSimulation


@dataclass
class ApiState:
    host: AgentHost
    settings: ModelSettings
    llm_factory: Callable[[str], ResilientLLM]
    persona_client: AuraPersonaClient | None = None
    personas: dict[str, PersonaSimulation] = field(default_factory=dict)  # running day replays, per user

    def personas_client(self) -> AuraPersonaClient:
        if self.persona_client is None:
            self.persona_client = AuraPersonaClient()
        return self.persona_client

    async def stop_persona(self, user_id: str) -> None:
        entry = self.personas.pop(user_id, None)
        if entry:
            await entry.stop()


def api_state(request: Request) -> ApiState:
    return request.app.state.api


async def user_agent(
    request: Request,
    user: str | None = Query(default=None),
    x_quintessa_user: str | None = Header(default=None),
) -> AgentRuntime:
    user_id = user or x_quintessa_user
    if not user_id:
        raise HTTPException(400, "name the user with ?user= or the X-Quintessa-User header")
    return await api_state(request).host.agent(user_id)


Api = Depends(api_state)
Agent = Depends(user_agent)
