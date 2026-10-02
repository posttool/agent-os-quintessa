from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import TYPE_CHECKING, Awaitable, Callable

from quintessa.models import InputEvent, InputKind
from quintessa.persona.client import AuraPersonaClient
from quintessa.persona.persona_observation import PersonaObservation
from quintessa.persona.persona_profile import PersonaProfile
from quintessa.serde import to_dict

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

# Aura observation types -> input kinds. Notifications from messaging apps
# are messages; everything else keeps its sensor meaning.
_KINDS = {
    "location": InputKind.LOCATION,
    "notification": InputKind.NOTIFICATION,
    "audio": InputKind.SPEECH,
    "screen": InputKind.SCREEN,
    "camera": InputKind.VISION,
    "wake": InputKind.SENSOR,
    "touch": InputKind.SENSOR,
    "motion": InputKind.SENSOR,
}


def to_event(obs: PersonaObservation) -> InputEvent:
    return InputEvent(
        kind=_KINDS.get(obs.type, InputKind.SENSOR),
        content=f"[{obs.date} {obs.time}] {obs.type}" + (f" from {obs.sender_app}" if obs.sender_app else "") + f": {obs.data}",
        source="persona",
        device=obs.device,
        sender=obs.sender,
    )


class PersonaSimulation:
    """Walks through a day in the life of a persona: clears the runtime, tells
    the agent who the user is, then replays the day's observations with their
    real gaps divided by `speed` (capped at `max_gap` seconds)."""

    def __init__(
        self,
        runtime: "AgentRuntime",
        client: AuraPersonaClient,
        *,
        speed: float = 600.0,
        max_gap: float = 30.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.runtime = runtime
        self.client = client
        self.speed = speed
        self.max_gap = max_gap
        self._sleep = sleep
        self._task: asyncio.Task | None = None

    async def start(self, persona_id: str, date: str | None = None) -> PersonaProfile:
        await self.stop()
        await self.runtime.clear()
        persona = await self.client.get_persona(persona_id)
        if date is None:
            days = await self.client.list_days(persona_id)
            date = days[0]["date"]
        observations = sorted(await self.client.list_observations(persona_id, date), key=lambda o: o.time)
        profile = {k: v for k, v in to_dict(persona).items() if k != "raw"}
        self.runtime.submit(
            InputEvent(InputKind.TEXT, "This is the user you are serving: " + json.dumps(profile), source="persona:profile")
        )
        self._task = asyncio.create_task(self._replay(observations))
        return persona

    async def _replay(self, observations: list[PersonaObservation]) -> None:
        previous: datetime | None = None
        for obs in observations:
            current = _parse_time(obs.time)
            if previous and current:
                await self._sleep(min((current - previous).total_seconds() / self.speed, self.max_gap))
            previous = current or previous
            self.runtime.submit(to_event(obs))

    async def wait(self) -> None:
        if self._task:
            await self._task

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%H:%M:%S")
    except ValueError:
        return None
