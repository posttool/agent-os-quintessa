from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from quintessa.api.app import create_app
from quintessa.apps import app_store_from_env
from quintessa.api.model_settings import ModelSettings
from quintessa.api.unconfigured import UnconfiguredLLM
from quintessa.decide import jev_options_from_env
from quintessa.host import AgentHost
from quintessa.llm import LLMError, ModelRoute, ResilientLLM
from quintessa.llm.factory import DEFAULT_CHAIN, build_llm
from quintessa.state import FileStateBackend
from quintessa.tools.search import search_backend_from_env

WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def build_app(data_dir: str | Path = "data") -> FastAPI:
    """The production wiring: file-backed per-user state under data_dir,
    the model chain from the environment, the built web app if present."""
    chain = os.environ.get("QUINTESSA_MODEL_CHAIN", DEFAULT_CHAIN)
    settings = ModelSettings(chain=chain.split(","))
    try:
        llm = build_llm(chain)
    except (LLMError, ValueError) as e:
        llm = ResilientLLM([ModelRoute(UnconfiguredLLM(str(e)), "none")])
        settings.status = str(e)
    settings.retries, settings.base_delay = llm.retries, llm.base_delay

    search = search_backend_from_env()
    host = AgentHost(
        llm, FileStateBackend(Path(data_dir) / "agents"), data_dir=data_dir, search=search, apps=app_store_from_env(search, llm),
        **jev_options_from_env(),
    )
    app = create_app(host, settings=settings, static_dir=os.environ.get("QUINTESSA_WEB_DIST", WEB_DIST))

    app.router.on_shutdown.append(host.shutdown)  # save everyone's state on the way down
    return app
