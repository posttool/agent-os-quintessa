from __future__ import annotations

from typing import Any, Callable

from quintessa.device.brief_item import BriefItem
from quintessa.device.device_state import DeviceState
from quintessa.device.discovery_item import DiscoveryItem
from quintessa.serde import to_dict

Listener = Callable[[str, dict[str, Any]], None]


class DeviceSurface:
    """The device the agent inhabits. The device tool and the loop write here;
    a skin (the web app's phone panel, glasses, a watch) listens and draws."""

    def __init__(self) -> None:
        self.state = DeviceState()
        self._listeners: list[Listener] = []
        self._active_sessions: dict[str, str] = {}

    def listen(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _emit(self, kind: str) -> None:
        payload = to_dict(self.state)
        for listener in self._listeners:
            listener(kind, payload)

    def load_state(self, state: DeviceState) -> None:
        self.state = state
        self._active_sessions.clear()
        self._emit("loaded")

    def reset(self) -> None:
        self.state = DeviceState()
        self._active_sessions.clear()
        self._emit("reset")

    def session_activity(self, session_id: str, words: str | None) -> None:
        """Island shows the latest activity of any running session."""
        if words:
            self._active_sessions[session_id] = words
        else:
            self._active_sessions.pop(session_id, None)
        latest = list(self._active_sessions.values())
        self.state.island.active = bool(latest)
        self.state.island.words = latest[-1] if latest else ""
        self._emit("island")

    def set_brief(self, items: list[BriefItem]) -> None:
        self.state.brief = items
        self._emit("brief")

    def show_ux(self, ux_request_id: str) -> None:
        self.state.open_ux_ids.append(ux_request_id)
        self._emit("ux_open")

    def close_ux(self, ux_request_id: str, document_id: str | None, section_id: str | None) -> None:
        if ux_request_id in self.state.open_ux_ids:
            self.state.open_ux_ids.remove(ux_request_id)
        if document_id:
            self.show_document(document_id, section_id)
        self._emit("ux_closed")

    def show_document(self, document_id: str, section_id: str | None = None) -> None:
        if document_id not in self.state.space_document_ids:
            self.state.space_document_ids.append(document_id)
        self.state.focused_document_id = document_id
        self.state.focused_section_id = section_id
        self._emit("space")

    def add_discovery(self, item: DiscoveryItem) -> None:
        self.state.discovery.append(item)
        self._emit("discovery")

    def notify(self, text: str) -> None:
        self.state.notifications.append(text)
        self._emit("notification")
