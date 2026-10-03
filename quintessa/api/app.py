"""HTTP API for the test harness web app. Every route acts on one user's
agent, named by the `user` query parameter or the X-Quintessa-User header.

The host trusts that id: put authentication in front of this before it
faces anyone but its developers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from quintessa.ambient import ambient_templates, source_from_description, source_from_template
from quintessa.api.model_settings import ModelSettings
from quintessa.apps.installer import install_app, installed_app, uninstall_app
from quintessa.api.unconfigured import UnconfiguredLLM
from quintessa.device import FOCUSED, FULL, DocumentFocus
from quintessa.device.focus import is_stale
from quintessa.host import AgentHost
from quintessa.llm import LLMError, ModelRoute, ResilientLLM
from quintessa.llm.catalog import model_catalog
from quintessa.llm.factory import build_llm
from quintessa.loop.runtime import AgentRuntime
from quintessa.models import (
    AmbientSource,
    AppListing,
    InputEvent,
    InputKind,
    OversightLevel,
    Tool,
    ToolFunction,
    ToolKind,
    ToolParameter,
    UXResponse,
)
from quintessa.persona import AuraPersonaClient, PersonaProfile, PersonaSimulation
from quintessa.serde import to_dict
from quintessa.state import StateFormatError
from quintessa.clock import now

HEARTBEAT_SECONDS = 15.0


# --- request bodies ---------------------------------------------------------------


class InputBody(BaseModel):
    kind: InputKind = InputKind.TEXT
    content: str
    sender: str = ""
    device: str = "phone"


class AnswerBody(BaseModel):
    values: dict[str, str] = {}
    dismissed: bool = False
    surface_context: str = ""


class ViewBody(BaseModel):
    document_id: str
    section_ids: list[str] | None = None  # None: drop the user's choice and refocus
    mode: str = FOCUSED


class ParameterBody(BaseModel):
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True


class FunctionBody(BaseModel):
    name: str
    description: str = ""
    parameters: list[ParameterBody] = []
    returns: str = "string"
    oversight: OversightLevel = OversightLevel.AUTO
    long_running: bool = False


class ToolBody(BaseModel):
    name: str
    description: str
    kind: ToolKind = ToolKind.LLM
    functions: list[FunctionBody] = []
    grounding: str = ""
    endpoint: str = ""
    code: str = ""


class SourceBody(BaseModel):
    name: str
    kind: InputKind
    events: list[str]
    interval_seconds: float = 5.0
    device: str = "phone"
    sender: str = ""
    loop: bool = False


class TemplateSourceBody(BaseModel):
    template: str
    count: int = 6


class VibeSourceBody(BaseModel):
    description: str
    count: int = 8


class SourcePatch(BaseModel):
    speed: float | None = None
    enabled: bool | None = None


class EnabledBody(BaseModel):
    enabled: bool


class PersonaStartBody(BaseModel):
    persona_id: str
    date: str | None = None
    speed: float = 600.0


class PreferencesBody(BaseModel):
    """Only the fields sent change; null returns a setting to the platform default."""

    jev: bool | None = None
    jev_shadow: bool | None = None
    jev_filter: bool | None = None
    jev_drive: bool | None = None
    ask_before_install: bool | None = None


class AppListingBody(BaseModel):
    app_id: str
    title: str
    store: str = ""
    developer: str = ""
    icon_url: str = ""
    category: str = ""
    rating: float | None = None
    store_url: str = ""
    summary: str = ""


class SettingsBody(BaseModel):
    chain: list[str]
    retries: int = 2
    base_delay: float = 1.0


# --- app ----------------------------------------------------------------------------


def create_app(
    host: AgentHost,
    *,
    settings: ModelSettings | None = None,
    llm_factory: Callable[[str], ResilientLLM] = build_llm,
    persona_client: AuraPersonaClient | None = None,
    static_dir: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Quintessa")
    settings = settings or ModelSettings(chain=[r.label for r in host.llm.routes])
    personas: dict[str, tuple[PersonaSimulation, PersonaProfile, str | None]] = {}

    def personas_client() -> AuraPersonaClient:
        nonlocal persona_client
        if persona_client is None:
            persona_client = AuraPersonaClient()
        return persona_client

    async def user_agent(
        user: str | None = Query(default=None),
        x_quintessa_user: str | None = Header(default=None),
    ) -> AgentRuntime:
        user_id = user or x_quintessa_user
        if not user_id:
            raise HTTPException(400, "name the user with ?user= or the X-Quintessa-User header")
        return await host.agent(user_id)

    Agent = Depends(user_agent)

    def persona_profile(agent: AgentRuntime) -> dict[str, Any] | None:
        entry = personas.get(agent.user_id)
        if entry is None:
            return None
        return {k: v for k, v in to_dict(entry[1]).items() if k != "raw"}

    # --- state -------------------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "users_loaded": host.loaded_users}

    @app.get("/api/state")
    async def state(agent: AgentRuntime = Agent) -> dict[str, Any]:
        entry = personas.get(agent.user_id)
        return {
            "user_id": agent.user_id,
            "memory": agent.store.to_data(),
            "device": to_dict(agent.device.state),
            "views": agent.document_views(),
            "pending_ux": [to_dict(r) for r in agent.ux.pending.values()],
            "ambient": {
                "enabled": agent.ambient.enabled,
                "sources": [
                    {**to_dict(s), "done": agent.ambient.source_done(s.id)} for s in agent.ambient.sources.values()
                ],
            },
            "persona": None if entry is None else {
                "profile": persona_profile(agent),
                "date": entry[2],
                "running": entry[0].running,
            },
            "settings": to_dict(settings),
            "jev": agent.jev_status(),
            "apps": {"store": agent.apps.name, "ask_before_install": agent.preference("ask_before_install")},
            "server_time": now().isoformat(),
        }

    @app.get("/api/stream")
    async def stream(request: Request, agent: AgentRuntime = Agent) -> StreamingResponse:
        """Server-sent events: a `change` whenever this user's agent changes."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)

        def watcher() -> None:
            if queue.empty():
                queue.put_nowait("change")

        async def events():
            agent.watchers.add(watcher)
            try:
                yield "event: change\ndata: {}\n\n"
                while not await request.is_disconnected():
                    try:
                        kind = await asyncio.wait_for(queue.get(), HEARTBEAT_SECONDS)
                        yield f"event: {kind}\ndata: {{}}\n\n"
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
            finally:
                agent.watchers.discard(watcher)

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    # --- the agent ---------------------------------------------------------------

    @app.post("/api/input")
    async def send_input(body: InputBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
        session = agent.submit(InputEvent(body.kind, body.content, source="user", device=body.device, sender=body.sender))
        return {"session_id": session.id}

    @app.post("/api/ux/{request_id}")
    async def answer(request_id: str, body: AnswerBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
        response = UXResponse(request_id, body.values, body.dismissed, body.surface_context)
        if not agent.answer(response):
            raise HTTPException(404, "that question is no longer waiting for an answer")
        return {"ok": True}

    @app.post("/api/view")
    async def view(body: ViewBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
        """The user opened a document, expanded sections or asked for all of
        it. Their choice holds until another part of the document changes."""
        doc = agent.store.documents.get(body.document_id)
        if doc is None:
            raise HTTPException(404, "no such document")
        if body.mode not in (FOCUSED, FULL):
            raise HTTPException(422, f"mode must be {FOCUSED!r} or {FULL!r}")
        if body.section_ids is None:
            agent.device.clear_focus(doc.id)
            return agent.document_views()[doc.id]
        unknown = [sid for sid in body.section_ids if doc.section(sid) is None]
        if unknown:
            raise HTTPException(422, f"no sections {unknown}")
        agent.device.show_document(doc.id, body.section_ids, body.mode, set_by="user")
        return agent.document_views()[doc.id]

    @app.post("/api/topics/{topic_id}/seen")
    async def topic_seen(topic_id: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
        topic = agent.store.topics.get(topic_id)
        if topic is None:
            raise HTTPException(404, "no such topic")
        # Keep showing what the user just opened to, rather than refocusing
        # the moment those sections stop counting as new.
        doc = agent.store.documents.get(topic.document_id or "")
        if doc is not None:
            focus = agent.device.state.focus.get(doc.id)
            if focus is None or is_stale(doc, focus):
                shown = agent.document_views()[doc.id]
                agent.device.pin_focus(DocumentFocus(doc.id, shown["section_ids"], shown["mode"], "", "rule"))
        topic.last_seen_at, topic.new_info = now(), ""
        agent.store.upsert_topic(topic)
        return {"ok": True}

    @app.post("/api/clear")
    async def clear(agent: AgentRuntime = Agent) -> dict[str, Any]:
        entry = personas.pop(agent.user_id, None)
        if entry:
            await entry[0].stop()
        await host.clear(agent.user_id)
        return {"ok": True}

    @app.get("/api/export")
    async def export(agent: AgentRuntime = Agent) -> JSONResponse:
        data = await host.export_state(agent.user_id)
        filename = f"quintessa-{agent.user_id}-{now().strftime('%Y%m%d-%H%M%S')}.json"
        return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.post("/api/restore")
    async def restore(request: Request, agent: AgentRuntime = Agent) -> dict[str, Any]:
        try:
            data = json.loads(await request.body())
        except json.JSONDecodeError as e:
            raise HTTPException(400, "the file is not JSON") from e
        entry = personas.pop(agent.user_id, None)
        if entry:
            await entry[0].stop()
        try:
            await host.restore_state(agent.user_id, data)
        except StateFormatError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True}

    # --- tools -------------------------------------------------------------------

    @app.post("/api/tools")
    async def put_tool(body: ToolBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
        existing = agent.store.tools.get(body.name)
        if body.kind == ToolKind.BUILTIN or (existing and existing.kind == ToolKind.BUILTIN):
            raise HTTPException(400, "built-in tools cannot be replaced")
        if body.kind == ToolKind.APP or (existing and existing.kind == ToolKind.APP):
            raise HTTPException(400, "apps are installed from the app store, not edited")
        agent.store.put_tool(
            Tool(
                name=body.name,
                description=body.description,
                kind=body.kind,
                grounding=body.grounding,
                endpoint=body.endpoint,
                code=body.code,
                created_by="user",
                functions=[
                    ToolFunction(
                        f.name,
                        f.description,
                        [ToolParameter(p.name, p.type, p.description, p.required) for p in f.parameters],
                        f.returns,
                        f.oversight,
                        f.long_running,
                    )
                    for f in body.functions
                ],
            )
        )
        return {"ok": True}

    @app.delete("/api/tools/{name}")
    async def delete_tool(name: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
        tool = agent.store.tools.get(name)
        if tool is None:
            raise HTTPException(404, "no such tool")
        if tool.kind == ToolKind.BUILTIN:
            raise HTTPException(400, "built-in tools cannot be deleted")
        agent.store.delete_tool(name)
        return {"ok": True}

    # --- apps --------------------------------------------------------------------

    @app.get("/api/apps/search")
    async def search_apps(q: str = Query(min_length=1), agent: AgentRuntime = Agent) -> list[dict[str, Any]]:
        listings = await agent.apps.search(q)
        return [
            {**to_dict(listing), "installed_as": t.name if (t := installed_app(agent.store, listing.app_id)) else None}
            for listing in listings
        ]

    @app.post("/api/apps/install")
    async def install(body: AppListingBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
        try:
            tool = await install_app(agent, AppListing(**body.model_dump()), created_by="user")
        except LLMError as e:
            raise HTTPException(502, f"could not write the app's manifest: {e}") from e
        return to_dict(tool)

    @app.delete("/api/apps/{app_id}")
    async def uninstall(app_id: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
        if uninstall_app(agent.store, app_id) is None:
            raise HTTPException(404, "that app is not installed")
        return {"ok": True}

    # --- ambient data ------------------------------------------------------------

    @app.get("/api/ambient/templates")
    async def templates() -> list[dict[str, Any]]:
        return ambient_templates()

    @app.put("/api/ambient/enabled")
    async def set_enabled(body: EnabledBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
        agent.ambient.set_enabled(body.enabled)
        return {"ok": True}

    @app.post("/api/ambient/sources")
    async def add_source(body: SourceBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
        source = AmbientSource(body.name, body.kind, body.events, body.interval_seconds, device=body.device,
                               sender=body.sender, loop=body.loop)
        agent.ambient.add_source(source)
        return {"id": source.id}

    @app.post("/api/ambient/sources/from-template")
    async def add_from_template(body: TemplateSourceBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
        template = next((t for t in ambient_templates() if t["name"] == body.template), None)
        if template is None:
            raise HTTPException(404, "no such template")
        try:
            source = await source_from_template(agent.llm, template, persona_profile(agent), body.count)
        except LLMError as e:
            raise HTTPException(502, str(e)) from e
        agent.ambient.add_source(source)
        return {"id": source.id}

    @app.post("/api/ambient/sources/vibe")
    async def add_vibe(body: VibeSourceBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
        try:
            source = await source_from_description(agent.llm, body.description, persona_profile(agent), body.count)
        except LLMError as e:
            raise HTTPException(502, str(e)) from e
        agent.ambient.add_source(source)
        return {"id": source.id}

    @app.patch("/api/ambient/sources/{source_id}")
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

    @app.delete("/api/ambient/sources/{source_id}")
    async def delete_source(source_id: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
        agent.ambient.remove_source(source_id)
        return {"ok": True}

    # --- personas ----------------------------------------------------------------

    @app.get("/api/personas")
    async def list_personas() -> list[dict[str, Any]]:
        try:
            people = await personas_client().list_personas()
        except Exception as e:  # network or service errors surface to the picker
            raise HTTPException(502, f"could not reach the Aura persona service: {e}") from e
        return [{k: v for k, v in to_dict(p).items() if k != "raw"} for p in people]

    @app.post("/api/persona/start")
    async def start_persona(body: PersonaStartBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
        previous = personas.pop(agent.user_id, None)
        if previous:
            await previous[0].stop()
        sim = PersonaSimulation(agent, personas_client(), speed=body.speed)
        try:
            profile = await sim.start(body.persona_id, body.date)
        except Exception as e:
            raise HTTPException(502, f"could not start the persona: {e}") from e
        personas[agent.user_id] = (sim, profile, sim.date)
        agent.notify_changed()
        return {"ok": True, "date": sim.date}

    @app.post("/api/persona/stop")
    async def stop_persona(agent: AgentRuntime = Agent) -> dict[str, Any]:
        entry = personas.get(agent.user_id)
        if entry:
            await entry[0].stop()
            agent.notify_changed()
        return {"ok": True}

    # --- preferences -------------------------------------------------------------

    @app.put("/api/preferences")
    async def put_preferences(body: PreferencesBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
        agent.set_preferences(**body.model_dump(exclude_unset=True))
        return agent.jev_status()

    # --- model settings ----------------------------------------------------------

    @app.get("/api/models")
    async def models() -> list[dict[str, Any]]:
        return model_catalog()

    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        return to_dict(settings)

    @app.put("/api/settings")
    async def put_settings(body: SettingsBody) -> dict[str, Any]:
        chain = [c.strip() for c in body.chain if c.strip()]
        if not chain:
            raise HTTPException(400, "the model chain needs at least one provider:model")
        try:
            built = llm_factory(",".join(chain))
            routes = built.routes
            settings.status = ""
        except (LLMError, ValueError) as e:
            routes = [ModelRoute(UnconfiguredLLM(str(e)), "none")]
            settings.status = str(e)
        host.llm.routes = routes
        host.llm.retries = max(body.retries, 0)
        host.llm.base_delay = max(body.base_delay, 0.0)
        settings.chain, settings.retries, settings.base_delay = chain, host.llm.retries, host.llm.base_delay
        for user_id in host.loaded_users:  # settings are platform-wide; refresh every open view
            for watcher in list((await host.agent(user_id)).watchers):
                watcher()
        return to_dict(settings)

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
