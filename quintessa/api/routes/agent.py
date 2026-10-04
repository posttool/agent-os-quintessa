"""Routes for one user's agent as a whole: its state and live updates, input,
what Spaces shows, clearing, download and restore, and Jev preferences."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from quintessa.api.bodies import InputBody, PreferencesBody, ViewBody
from quintessa.api.deps import Agent, Api, ApiState
from quintessa.clock import now
from quintessa.device import FOCUSED, FULL, FocusSource
from quintessa.loop.runtime import AgentRuntime
from quintessa.models import InputEvent
from quintessa.serde import to_dict
from quintessa.state import StateFormatError

HEARTBEAT_SECONDS = 15.0

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(api: ApiState = Api) -> dict[str, Any]:
    return {"ok": True, "users_loaded": api.host.loaded_users}


@router.get("/state")
async def state(agent: AgentRuntime = Agent, api: ApiState = Api) -> dict[str, Any]:
    entry = api.personas.get(agent.user_id)
    agent.device.prune_brief(now())
    agent.prune_stash()
    return {
        "user_id": agent.user_id,
        "memory": agent.store.to_data(),
        "device": to_dict(agent.device.state),
        "views": agent.document_views(),
        "questions": [to_dict(r) for r in agent.questions.pending.values()],
        "ambient": {
            "enabled": agent.ambient.enabled,
            "sources": [
                {**to_dict(s), "done": agent.ambient.source_done(s.id)} for s in agent.ambient.sources.values()
            ],
        },
        "persona": None
        if agent.persona is None
        else {
            "profile": agent.persona["profile"],
            "date": agent.persona.get("date"),
            "running": entry is not None and entry.running,
        },
        "settings": to_dict(api.settings),
        "jev": agent.jev_status(),
        "apps": {"store": agent.apps.name},
        "server_time": now().isoformat(),
    }


@router.get("/stream")
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
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            agent.watchers.discard(watcher)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/input")
async def send_input(body: InputBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
    session = agent.submit(InputEvent(body.kind, body.content, source="user", device=body.device, sender=body.sender))
    return {"session_id": session.id}


@router.post("/view")
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
    agent.device.show_document(doc.id, body.section_ids, body.mode, set_by=FocusSource.USER)
    return agent.document_views()[doc.id]


@router.post("/topics/{topic_id}/seen")
async def topic_seen(topic_id: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
    if not agent.mark_topic_seen(topic_id):
        raise HTTPException(404, "no such topic")
    return {"ok": True}


@router.post("/clear")
async def clear(agent: AgentRuntime = Agent, api: ApiState = Api) -> dict[str, Any]:
    await api.stop_persona(agent.user_id)
    await api.host.clear(agent.user_id)
    return {"ok": True}


@router.get("/export")
async def export(agent: AgentRuntime = Agent, api: ApiState = Api) -> JSONResponse:
    data = await api.host.export_state(agent.user_id)
    filename = f"quintessa-{agent.user_id}-{now().strftime('%Y%m%d-%H%M%S')}.json"
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/restore")
async def restore(request: Request, agent: AgentRuntime = Agent, api: ApiState = Api) -> dict[str, Any]:
    try:
        data = json.loads(await request.body())
    except json.JSONDecodeError as e:
        raise HTTPException(400, "the file is not JSON") from e
    await api.stop_persona(agent.user_id)
    try:
        await api.host.restore_state(agent.user_id, data)
    except StateFormatError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@router.put("/preferences")
async def put_preferences(body: PreferencesBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
    agent.set_preferences(**body.model_dump(exclude_unset=True))
    return agent.jev_status()
