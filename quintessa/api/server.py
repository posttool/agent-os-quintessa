from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from quintessa import config
from quintessa.api.app import create_app
from quintessa.api.model_settings import ModelSettings
from quintessa.api.unconfigured import UnconfiguredLLM
from quintessa.apps import app_store_from_env
from quintessa.decide import jev_options_from_env
from quintessa.host import AgentHost
from quintessa.llm import LLMError, ModelRoute, ResilientLLM
from quintessa.llm.factory import DEFAULT_CHAIN, build_llm
from quintessa.state import state_backend_from_env
from quintessa.tools.picture_search import picture_search_from_env
from quintessa.tools.search import search_backend_from_env

WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def build_app(data_dir: str | Path = "data") -> FastAPI:
    """The production wiring: per-user state in the database (see
    state_backend_from_env), the model chain from the environment, the
    built web app if present."""
    chain = config.model_chain(DEFAULT_CHAIN)
    settings = ModelSettings(chain=chain.split(","))
    try:
        llm = build_llm(chain)
    except (LLMError, ValueError) as e:
        llm = ResilientLLM([ModelRoute(UnconfiguredLLM(str(e)), "none")])
        settings.status = str(e)
    settings.retries, settings.base_delay = llm.retries, llm.base_delay

    search = search_backend_from_env()
    backend = state_backend_from_env(data_dir)
    host = AgentHost(
        llm,
        backend,
        data_dir=data_dir,
        search=search,
        picture_search=picture_search_from_env(),
        apps=app_store_from_env(search, llm),
        **jev_options_from_env(),
    )
    app = create_app(host, settings=settings, static_dir=config.web_dist(WEB_DIST))

    app.router.on_shutdown.append(host.shutdown)  # save everyone's state on the way down
    if hasattr(backend, "close"):
        app.router.on_shutdown.append(backend.close)
    return app
