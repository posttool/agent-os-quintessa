from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Awaitable, Callable

from quintessa.ambient.bus import AmbientBus
from quintessa.capabilities.loader import load_capabilities, load_prompt
from quintessa.device import DeviceSurface
from quintessa.llm import ResilientLLM
from quintessa.loop.reasoning_loop import AgentReasoningLoop
from quintessa.loop.ux_broker import UXBroker
from quintessa.memory import MemoryStore
from quintessa.models import Capability, InputEvent, ReasoningSession, UXResponse
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
        process_interval: float = 5.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.user_id = user_id
        self.llm = llm
        self.store = store or MemoryStore()
        self.device = device or DeviceSurface()
        self.capabilities = capabilities or load_capabilities(capability_dir)
        self.controller_prompt = load_prompt("controller", capability_dir)
        self.max_steps = max_steps
        self.data_dir = Path(data_dir)
        self.search = search
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

    @property
    def busy(self) -> bool:
        return bool(self._tasks)

    def install_builtin_tools(self) -> None:
        for tool in BUILTIN_TOOLS:
            self.store.put_tool(copy.deepcopy(tool))

    def submit(self, event: InputEvent) -> ReasoningSession:
        """Start a reasoning session for this input and return it right away."""
        session = ReasoningSession(trigger=event)
        self.store.record_event(event)
        self.store.put_session(session)
        task = asyncio.create_task(AgentReasoningLoop(self, session).run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return session

    async def run(self, event: InputEvent) -> ReasoningSession:
        """Start a session and wait for it (and anything it spawned) to finish."""
        session = self.submit(event)
        await self.wait_idle()
        return session

    async def wait_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

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
        self.device.reset()
        self.install_builtin_tools()
