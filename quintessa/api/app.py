"""HTTP API for the test harness web app. Every route acts on one user's
agent, named by the `user` query parameter or the X-Quintessa-User header.

The host trusts that id: put authentication in front of this before it
faces anyone but its developers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from quintessa.api.deps import ApiState
from quintessa.api.model_settings import ModelSettings
from quintessa.api.routes import ROUTERS
from quintessa.host import AgentHost
from quintessa.llm import ResilientLLM
from quintessa.llm.factory import build_llm
from quintessa.persona import AuraPersonaClient


def create_app(
    host: AgentHost,
    *,
    settings: ModelSettings | None = None,
    llm_factory: Callable[[str], ResilientLLM] = build_llm,
    persona_client: AuraPersonaClient | None = None,
    static_dir: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Quintessa")
    app.state.api = ApiState(
        host,
        settings or ModelSettings(chain=[r.label for r in host.llm.routes]),
        llm_factory,
        persona_client,
    )
    for router in ROUTERS:
        app.include_router(router)

    # --- web app -----------------------------------------------------------------

    if static_dir and Path(static_dir).exists():
        static = Path(static_dir)
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}")
        async def spa(path: str) -> FileResponse:
            candidate = (static / path).resolve()
            if path and candidate.is_file() and static.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(static / "index.html")

    return app
