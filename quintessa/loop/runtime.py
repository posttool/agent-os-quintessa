from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from quintessa.ambient.bus import AmbientBus
from quintessa.apps import AppStore, OfflineCatalog
from quintessa.capabilities.loader import load_capabilities, load_prompt
from quintessa.decide import AmbientFilter, BriefRanker, NextStepDecider
from quintessa.device import DeviceSurface
from quintessa.device.focus import resolve_view
from quintessa.llm import ResilientLLM
from quintessa.loop.reasoning_loop import AgentReasoningLoop
from quintessa.loop.ux_broker import UXBroker
from quintessa.memory import MemoryStore
from quintessa.models import Capability, InputEvent, InputKind, Permission, Preferences, ReasoningSession, UXResponse
from quintessa.tools import BUILTIN_TOOLS
from quintessa.tools.search import SearchBackend


class AgentRuntime:
    """One user's agent: their memory, device surface, pending questions and
    process subscriptions. Runs any number of reasoning loops at once over
    that user's memory; sessions waiting on the user do not block the others.

    The platform holds one runtime per user through AgentHost."""

    def __init__(
        self,
        llm: ResilientLLM,
        *,
        user_id: str = "default",
        store: MemoryStore | None = None,
        device: DeviceSurface | None = None,
        capabilities: dict[str, Capability] | None = None,
        capability_dir: str | Path | None = None,
        max_steps: int = 12,
        data_dir: str | Path = "data",
        search: SearchBackend | None = None,
        apps: AppStore | None = None,
        process_interval: float = 5.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        shadow: NextStepDecider | None = None,
        ambient_filter: AmbientFilter | None = None,
        jev_shadow_default: bool = True,
        jev_filter_default: bool = True,
        brief_ranker: BriefRanker | None = None,
    ):
        self.user_id = user_id
        self.llm = llm
        self.store = store or MemoryStore()
        self.device = device or DeviceSurface()
        self.capabilities = capabilities or load_capabilities(capability_dir)
        self.controller_prompt = load_prompt("controller", capability_dir)
        self.max_steps = max_steps
        self.jev_shadow = shadow  # a System One model asked beside the LLM at each decision; never steers
        self.jev_filter = ambient_filter  # skips ambient events a System One model says do not matter
        self.jev_ranker = brief_ranker  # scores brief cards' urgency, context fit and person
        self.jev_defaults = Preferences(True, jev_shadow_default, jev_filter_default, False, True)
        self.preferences = Preferences()
        self.persona: dict[str, Any] | None = None  # the attached Aura persona: profile, persona_id, date
        self.data_dir = Path(data_dir)
        self.search = search
        self.apps = apps or OfflineCatalog()  # where tool discovery finds apps to install
        self.ux = UXBroker()
        self.ambient = AmbientBus(self, process_interval=process_interval, sleep=sleep)
        self._tasks: set[asyncio.Task] = set()
        self.on_change: Callable[[], None] | None = None
        self.watchers: set[Callable[[], None]] = set()
        self.store.listen(lambda *_: self.notify_changed())
        self.device.listen(lambda *_: self.notify_changed())
        self.ux.on_request(lambda _: self.notify_changed())
        self.install_builtin_tools()

    def notify_changed(self) -> None:
        """Something about this user's agent changed: persist it (on_change,
        set by the host) and tell live views (watchers)."""
        if self.on_change is not None:
            self.on_change()
        for watcher in list(self.watchers):
            watcher()

    def preference(self, name: str) -> bool:
        """The user's setting, or the platform default when they never chose."""
        value = getattr(self.preferences, name)
        return getattr(self.jev_defaults, name) if value is None else value

    def set_preferences(self, **changes: bool | None) -> None:
        for name, value in changes.items():
            setattr(self.preferences, name, value)
        self.notify_changed()

    @property
    def shadow(self) -> NextStepDecider | None:
        """The Jev next-step shadow, when configured and this user has it on."""
        return self.jev_shadow if self.preference("jev") and self.preference("jev_shadow") else None

    @property
    def driver(self) -> NextStepDecider | None:
        """Jev, when this user lets it pick the next step instead of the LLM."""
        return self.jev_shadow if self.preference("jev") and self.preference("jev_drive") else None

    @property
    def ambient_filter(self) -> AmbientFilter | None:
        """The Jev ambient filter, when configured and this user has it on."""
        return self.jev_filter if self.preference("jev") and self.preference("jev_filter") else None

    @property
    def brief_ranker(self) -> BriefRanker | None:
        """Jev scoring brief cards, when configured and this user has it on."""
        return self.jev_ranker if self.preference("jev") and self.preference("jev_rank") else None

    def jev_status(self) -> dict[str, Any]:
        decider = self.jev_shadow or self.jev_filter or self.jev_ranker
        return {
            "available": decider is not None,
            "model": decider.client.label if decider else "",
            "threshold": self.jev_filter.threshold if self.jev_filter else None,
            **{name: self.preference(name) for name in ("jev", "jev_shadow", "jev_filter", "jev_drive", "jev_rank")},
        }

    @property
    def busy(self) -> bool:
        return bool(self._tasks)

    def install_builtin_tools(self) -> None:
        for tool in BUILTIN_TOOLS:
            self.store.put_tool(copy.deepcopy(tool))

    def submit(self, event: InputEvent, grants: list[Permission] | None = None) -> ReasoningSession:
        """Start a reasoning session for this input and return it right away.
        Grants are approvals the user already gave with the input (a tapped
        brief action); they carry through the session like answered prompts."""
        session = ReasoningSession(trigger=event)
        for grant in grants or []:
            grant.session_id = session.id
            session.permissions.append(grant)
        self.store.record_event(event)
        self.store.put_session(session)
        task = asyncio.create_task(AgentReasoningLoop(self, session).run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return session

    def start_brief_action(self, item_id: str) -> ReasoningSession | None:
        """The user tapped a brief card's action. A reasoning session carries
        it out, holding the tap as approval for that one tool function so it
        is not asked about again; any other tool still asks as usual."""
        item = next((b for b in self.device.state.brief if b.id == item_id), None)
        if item is None or item.action is None:
            return None
        action = item.action
        about = ", ".join(f"{k}: {v}" for k, v in (("topic_id", item.topic_id), ("document_id", item.document_id),
                                                   ("section_id", item.section_id)) if v)
        content = (
            f'The user tapped "{action.label}" on the brief card "{item.text}"'
            + (f" ({about})" if about else "")
            + f". Do it now with {action.tool}.{action.function}"
            + (f" using {json.dumps(action.arguments)}" if action.arguments else "")
            + ". The tap approves that call."
        )
        grant = Permission(action.tool, action.function, True, "session", f'tapped "{action.label}" in the brief')
        return self.submit(InputEvent(InputKind.TEXT, content, source="user", device="phone"), grants=[grant])

    async def run(self, event: InputEvent) -> ReasoningSession:
        """Start a session and wait for it (and anything it spawned) to finish."""
        session = self.submit(event)
        await self.wait_idle()
        return session

    async def wait_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def document_views(self) -> dict[str, dict[str, Any]]:
        """For each live document, which sections Spaces shows expanded."""
        questions = list(self.ux.pending.values())
        return {
            doc.id: resolve_view(
                doc,
                self.device.state.focus.get(doc.id),
                questions,
                self.store.topics.get(doc.topic_id) if doc.topic_id else None,
            )
            for doc in self.store.documents.values()
            if doc.status.value != "archived"
        }

    def on_screen(self) -> dict[str, Any] | None:
        """The document open in Spaces and the parts of it the user sees."""
        doc_id = self.device.state.focused_document_id
        doc = self.store.documents.get(doc_id) if doc_id else None
        if doc is None or doc.status.value == "archived":
            return None
        return self.document_views()[doc.id]

    def answer(self, response: UXResponse) -> bool:
        return self.ux.answer(response)

    async def cancel_tasks(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def clear(self) -> None:
        """Clear memory, traces, tools, subscriptions and the device."""
        self.ambient.stop_all()
        self.ux.cancel_all()
        await self.cancel_tasks()
        self.store.clear()
        self.persona = None
        self.device.reset()
        self.install_builtin_tools()
