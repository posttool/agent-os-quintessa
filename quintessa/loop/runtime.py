from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quintessa.ambient.bus import AmbientBus
from quintessa.apps import AppStore, OfflineCatalog
from quintessa.capabilities.loader import load_capabilities, load_prompt
from quintessa.decide import AmbientFilter, CardScorer, JevSwitches, NextStepDecider
from quintessa.device import DeviceSurface, DocumentFocus, FocusSource
from quintessa.device.focus import is_stale, resolve_view
from quintessa.llm import ResilientLLM
from quintessa.loop.question_broker import QuestionBroker
from quintessa.loop.reasoning_loop import AgentReasoningLoop
from quintessa.memory import MemoryStore
from quintessa.models import (
    Answer,
    Capability,
    InputEvent,
    InputKind,
    Permission,
    PermissionScope,
    Preferences,
    ReasoningSession,
)
from quintessa.prompts import prompt
from quintessa.serde import to_dict
from quintessa.tools import BUILTIN_TOOLS
from quintessa.tools.picture_search import PictureSearch
from quintessa.tools.search import SearchBackend

if TYPE_CHECKING:
    from quintessa.persona import PersonaProfile


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
        picture_search: PictureSearch | None = None,
        apps: AppStore | None = None,
        process_interval: float = 5.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jev_next_step: NextStepDecider | None = None,
        jev_ambient_filter: AmbientFilter | None = None,
        jev_shadow_default: bool = True,
        jev_filter_default: bool = True,
        jev_card_scorer: CardScorer | None = None,
    ):
        self.user_id = user_id
        self.llm = llm
        self.store = store or MemoryStore()
        self.device = device or DeviceSurface()
        self.capabilities = capabilities or load_capabilities(capability_dir)
        self.controller_prompt = load_prompt("controller", capability_dir)
        self.max_steps = max_steps
        self.jev = JevSwitches(
            jev_next_step,
            jev_ambient_filter,
            jev_card_scorer,
            shadow_default=jev_shadow_default,
            filter_default=jev_filter_default,
        )
        self.preferences = Preferences()
        self.persona: dict[str, Any] | None = None  # the attached Aura persona: profile, persona_id, date
        self.data_dir = Path(data_dir)
        self.search = search
        self.picture_search = picture_search  # real pictures for what simulated tools describe
        self.apps = apps or OfflineCatalog()  # where tool discovery finds apps to install
        self.questions = QuestionBroker()
        self.ambient = AmbientBus(self, process_interval=process_interval, sleep=sleep)
        self._tasks: set[asyncio.Task] = set()
        # next-step questions from finished sessions; wait_idle does not wait on them
        self._follow_ups: set[asyncio.Task] = set()
        self.offered_steps: dict[str, tuple[str, ...]] = {}  # by document: the next steps last offered
        self.on_change: Callable[[], None] | None = None
        self.watchers: set[Callable[[], None]] = set()
        self.store.listen(lambda *_: self.notify_changed())
        self.device.listen(lambda *_: self.notify_changed())
        self.questions.on_question(lambda _: self.notify_changed())
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
        return self.jev.setting(self.preferences, name)

    def set_preferences(self, **changes: bool | None) -> None:
        for name, value in changes.items():
            setattr(self.preferences, name, value)
        self.notify_changed()

    @property
    def active_shadow(self) -> NextStepDecider | None:
        return self.jev.shadow(self.preferences)

    @property
    def active_driver(self) -> NextStepDecider | None:
        return self.jev.driver(self.preferences)

    @property
    def active_ambient_filter(self) -> AmbientFilter | None:
        return self.jev.active_ambient_filter(self.preferences)

    @property
    def active_card_scorer(self) -> CardScorer | None:
        return self.jev.active_card_scorer(self.preferences)

    def jev_status(self) -> dict[str, Any]:
        return self.jev.status(self.preferences)

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

    def start_card_action(self, card_id: str) -> ReasoningSession | None:
        """The user tapped a brief card's action. A reasoning session carries
        it out, holding the tap as approval for that one tool function so it
        is not asked about again; any other tool still asks as usual."""
        card = next((b for b in self.device.state.brief if b.id == card_id), None)
        if card is None or card.action is None:
            return None
        action = card.action
        about = ", ".join(
            f"{k}: {v}"
            for k, v in (
                ("topic_id", card.topic_id),
                ("document_id", card.document_id),
                ("section_id", card.section_id),
            )
            if v
        )
        content = prompt(
            "card_action",
            label=action.label,
            text=card.text,
            about=f" ({about})" if about else "",
            call=f"{action.tool}.{action.function}",
            arguments=f" using {json.dumps(action.arguments)}" if action.arguments else "",
        )
        grant = Permission(
            action.tool, action.function, True, PermissionScope.SESSION, f'tapped "{action.label}" in the brief'
        )
        return self.submit(InputEvent(InputKind.TEXT, content, source="user", device="phone"), grants=[grant])

    def follow_up(self, work: Awaitable[None]) -> None:
        """Wait on the user after a session ended, without keeping it running."""
        task = asyncio.ensure_future(work)
        self._follow_ups.add(task)
        task.add_done_callback(self._follow_ups.discard)

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
        questions = list(self.questions.pending.values())
        return {
            doc.id: resolve_view(
                doc,
                self.device.state.focus.get(doc.id),
                questions,
                self.store.topics.get(doc.topic_id) if doc.topic_id else None,
            )
            for doc in self.store.documents.values()
            if not doc.archived
        }

    def on_screen(self) -> dict[str, Any] | None:
        """The document open in Spaces and the parts of it the user sees."""
        doc_id = self.device.state.focused_document_id
        doc = self.store.documents.get(doc_id) if doc_id else None
        if doc is None or doc.archived:
            return None
        return self.document_views()[doc.id]

    def mark_topic_seen(self, topic_id: str) -> bool:
        """The user opened a topic. Spaces keeps showing what they opened to,
        rather than refocusing the moment those sections stop counting as new."""
        topic = self.store.topics.get(topic_id)
        if topic is None:
            return False
        doc = self.store.documents.get(topic.document_id or "")
        if doc is not None:
            focus = self.device.state.focus.get(doc.id)
            if focus is None or is_stale(doc, focus):
                shown = self.document_views()[doc.id]
                self.device.pin_focus(DocumentFocus(doc.id, shown["section_ids"], shown["mode"], "", FocusSource.RULE))
        self.store.mark_topic_seen(topic_id)
        return True

    def attach_persona(self, persona_id: str, date: str, profile: PersonaProfile) -> None:
        """Remember which Aura persona this agent is serving, for the UI and the saved state."""
        self.persona = {"persona_id": persona_id, "date": date, "profile": to_dict(profile.summary())}
        self.notify_changed()

    def answer(self, response: Answer) -> bool:
        return self.questions.answer(response)

    def stash_question(self, question_id: str) -> bool:
        """The user put a waiting question aside; its session keeps waiting."""
        request = self.questions.pending.get(question_id)
        if request is None:
            return False
        self.device.stash(request.id, request.topic_id)
        return True

    def prune_stash(self) -> list[str]:
        """Drop stashed questions that stopped waiting and bring back those
        whose topic changed since they were stashed."""

        def changed(topic_id: str, since) -> bool:
            topic = self.store.topics.get(topic_id)
            return topic is not None and topic.updated_at > since

        return self.device.prune_stash(set(self.questions.pending), changed)

    async def cancel_tasks(self) -> None:
        tasks = [*self._tasks, *self._follow_ups]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def clear(self) -> None:
        """Clear memory, traces, tools, subscriptions and the device."""
        self.ambient.stop_all()
        self.questions.cancel_all()
        await self.cancel_tasks()
        self.store.clear()
        self.persona = None
        self.offered_steps.clear()
        self.device.reset()
        self.install_builtin_tools()
