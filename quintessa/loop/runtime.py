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
    """Runs any number of reasoning loops at once over one shared memory.
    Every input starts its own session; sessions waiting on the user do not
    block the others."""

    def __init__(
        self,
        llm: ResilientLLM,
        *,
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
        self._install_builtin_tools()

    def _install_builtin_tools(self) -> None:
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

    async def clear(self) -> None:
        """Clear memory, traces, tools, subscriptions and the device."""
        self.ambient.stop_all()
        self.ux.cancel_all()
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)
        self.store.clear()
        self.device.reset()
        self._install_builtin_tools()
