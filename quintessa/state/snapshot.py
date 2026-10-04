"""The portable form of one user's agent state: memory (graph, topics,
documents, tools, permissions, processes, events, traces), what the
device was showing, the user's preferences and the Aura persona they
attached. The same format is used for durable storage and for user
download / restore."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from quintessa.clock import now
from quintessa.device import DeviceState
from quintessa.memory import MemoryStore
from quintessa.models import Preferences, SessionStatus, TraceStep
from quintessa.serde import from_dict, to_dict

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

FORMAT = "quintessa.agent-state"
VERSION = 2
INTERRUPTED = "interrupted: the platform restarted while this session was running"


class StateFormatError(ValueError):
    """The data is not a Quintessa agent state this version can read."""


def take_snapshot(runtime: AgentRuntime) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "version": VERSION,
        "user_id": runtime.user_id,
        "saved_at": now().isoformat(),
        "memory": runtime.store.to_data(),
        "device": to_dict(runtime.device.state),
        "preferences": to_dict(runtime.preferences),
        "persona": runtime.persona,
    }


def upgrade_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """Bring an older snapshot up to VERSION. Version 1 called questions
    "UX requests", cards "brief items" and the ambient filter "prefilter"."""
    if data.get("version") != 1:
        return data
    data = {**data, "version": 2}
    memory, device = data.get("memory"), data.get("device")
    if isinstance(memory, dict) and isinstance(memory.get("sessions"), list):
        names = {"pending_ux_id": "pending_question_id", "prefilter": "ambient_filter"}
        sessions = [_renamed(s, **names) for s in memory["sessions"]]
        data["memory"] = {**memory, "sessions": sessions}
    if isinstance(device, dict):
        device = _renamed(device, open_ux_ids="open_question_ids")
        for key in ("brief", "snoozed", "stashed"):
            if isinstance(device.get(key), list):
                device[key] = [_renamed(c, ux_request_id="question_id") for c in device[key]]
        data["device"] = device
    return data


def _renamed(item: Any, **names: str) -> Any:
    return {names.get(k, k): v for k, v in item.items()} if isinstance(item, dict) else item


def check_snapshot(data: Any) -> None:
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise StateFormatError("not a Quintessa agent state")
    if data.get("version") != VERSION:
        raise StateFormatError(f"unsupported agent state version {data.get('version')!r} (expected {VERSION})")
    for key in ("memory", "device"):
        if not isinstance(data.get(key), dict):
            raise StateFormatError(f"agent state is missing {key!r}")


def validate_snapshot(data: Any) -> None:
    """Fully check a snapshot (by loading it into scratch memory) without
    touching any agent, so a bad upload never wipes good state."""
    if isinstance(data, dict) and data.get("format") == FORMAT:
        data = upgrade_snapshot(data)
    check_snapshot(data)
    try:
        MemoryStore().load_data(data["memory"])
        from_dict(DeviceState, data["device"])
        from_dict(Preferences, data.get("preferences") or {})
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise StateFormatError(f"agent state is damaged: {e}") from e


def apply_snapshot(runtime: AgentRuntime, data: dict[str, Any]) -> None:
    """Load a snapshot into an idle runtime. Sessions that were mid-flight
    when it was taken are marked stopped (their in-memory continuation is
    gone); process subscriptions that were still running resume."""
    data = upgrade_snapshot(data)
    validate_snapshot(data)
    runtime.store.load_data(data["memory"])
    device = from_dict(DeviceState, data["device"])
    device.open_question_ids = []
    device.island.active, device.island.words = False, ""
    runtime.device.load_state(device)
    if data.get("preferences"):  # states saved before preferences existed keep the current ones
        runtime.preferences = from_dict(Preferences, data["preferences"])
    runtime.persona = data.get("persona")
    runtime.install_builtin_tools()
    for session in runtime.store.sessions.values():
        if session.status in (SessionStatus.RUNNING, SessionStatus.WAITING_FOR_USER):
            session.status = SessionStatus.STOPPED
            session.pending_question_id = None
            session.ended_at = now()
            session.steps.append(TraceStep(len(session.steps), "", "", "", error=INTERRUPTED, ended_at=now()))
    for subscription in runtime.store.subscriptions.values():
        if not subscription.archived:
            runtime.ambient.follow(subscription)
