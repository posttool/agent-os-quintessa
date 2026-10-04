"""Searching the app store, installing and uninstalling apps."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from quintessa.api.bodies import AppListingBody
from quintessa.api.deps import Agent
from quintessa.apps.installer import install_app, installed_app, uninstall_app
from quintessa.llm import LLMError
from quintessa.loop.runtime import AgentRuntime
from quintessa.models import AppListing, ToolAuthor
from quintessa.serde import to_dict

router = APIRouter(prefix="/api")


@router.get("/apps/search")
async def search_apps(q: str = Query(min_length=1), agent: AgentRuntime = Agent) -> list[dict[str, Any]]:
    listings = await agent.apps.search(q)
    return [
        {**to_dict(listing), "installed_as": t.name if (t := installed_app(agent.store, listing.app_id)) else None}
        for listing in listings
    ]


@router.post("/apps/install")
async def install(body: AppListingBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
    try:
        tool = await install_app(agent, AppListing(**body.model_dump()), created_by=ToolAuthor.USER)
    except LLMError as e:
        raise HTTPException(502, f"could not write the app's manifest: {e}") from e
    return to_dict(tool)


@router.delete("/apps/{app_id}")
async def uninstall(app_id: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
    if uninstall_app(agent.store, app_id) is None:
        raise HTTPException(404, "that app is not installed")
    return {"ok": True}
