"""The platform-wide model chain and the models users can pick from."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from quintessa.api.bodies import SettingsBody
from quintessa.api.deps import Api, ApiState
from quintessa.api.unconfigured import UnconfiguredLLM
from quintessa.llm import LLMError, ModelRoute
from quintessa.llm.catalog import model_catalog
from quintessa.serde import to_dict

router = APIRouter(prefix="/api")


@router.get("/models")
async def models() -> list[dict[str, Any]]:
    return model_catalog()


@router.get("/settings")
async def get_settings(api: ApiState = Api) -> dict[str, Any]:
    return to_dict(api.settings)


@router.put("/settings")
async def put_settings(body: SettingsBody, api: ApiState = Api) -> dict[str, Any]:
    chain = [c.strip() for c in body.chain if c.strip()]
    if not chain:
        raise HTTPException(400, "the model chain needs at least one provider:model")
    settings = api.settings
    try:
        routes = api.llm_factory(",".join(chain)).routes
        settings.status = ""
    except (LLMError, ValueError) as e:  # keep the chain the user typed; calls fail with the reason
        routes = [ModelRoute(UnconfiguredLLM(str(e)), "none")]
        settings.status = str(e)
    api.host.set_model_chain(routes, body.retries, body.base_delay)
    settings.chain, settings.retries, settings.base_delay = chain, api.host.llm.retries, api.host.llm.base_delay
    return to_dict(settings)
