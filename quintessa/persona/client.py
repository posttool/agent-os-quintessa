from __future__ import annotations

from typing import Any

import httpx

from quintessa import config
from quintessa.persona.persona_observation import PersonaObservation
from quintessa.persona.persona_profile import PersonaProfile

DEFAULT_BASE_URL = "https://us-central1-aura-persona.cloudfunctions.net"


class AuraPersonaClient:
    """Read-only client for the Aura persona Cloud Functions (Firebase
    callable protocol: POST {"data": ...} -> {"result": ...}).

    Base URL comes from AURA_PERSONA_BASE_URL; for the local emulator use
    http://localhost:5001/aura-persona/us-central1."""

    def __init__(self, base_url: str | None = None, http: httpx.AsyncClient | None = None):
        self.base_url = (base_url or config.persona_base_url(DEFAULT_BASE_URL)).rstrip("/")
        self.http = http or httpx.AsyncClient(timeout=30)

    async def _call(self, function: str, data: dict[str, Any]) -> Any:
        response = await self.http.post(f"{self.base_url}/{function}", json={"data": data})
        response.raise_for_status()
        return response.json()["result"]

    async def list_personas(self, limit: int = 50) -> list[PersonaProfile]:
        return [_profile(p) for p in await self._call("listPersona", {"limit": limit})]

    async def get_persona(self, persona_id: str) -> PersonaProfile:
        return _profile(await self._call("getPersona", {"id": persona_id}))

    async def list_days(self, persona_id: str) -> list[dict[str, Any]]:
        return await self._call("listDaysForPersona", {"id": persona_id})

    async def list_observations(self, persona_id: str, date: str) -> list[PersonaObservation]:
        rows = await self._call("listObservations", {"id": persona_id, "date": date})
        return [
            PersonaObservation(
                date=r.get("date", date),
                time=r.get("time", ""),
                device=r.get("device", ""),
                type=r.get("type", ""),
                data=str(r.get("data", "")),
                sender_app=r.get("senderApp", ""),
                sender=r.get("sender", ""),
                id=r.get("id", ""),
            )
            for r in rows
        ]


def _profile(p: dict[str, Any]) -> PersonaProfile:
    return PersonaProfile(
        id=p["id"],
        name=p.get("name", ""),
        occupation=p.get("occupation", ""),
        city=p.get("city", ""),
        age=p.get("age"),
        hobbies=p.get("hobbies"),
        goals_this_week=p.get("goals_this_week"),
        family=p.get("family"),
        apps=p.get("apps") or p.get("apps_and_services"),
        image=p.get("image", ""),
        raw=p,
    )
