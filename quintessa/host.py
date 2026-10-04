from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from quintessa.llm import ModelRoute, ResilientLLM
from quintessa.loop.runtime import AgentRuntime
from quintessa.models import Answer, InputEvent, ReasoningSession
from quintessa.state.snapshot import apply_snapshot, take_snapshot, validate_snapshot
from quintessa.state.state_backend import StateBackend

log = logging.getLogger(__name__)


class AgentHost:
    """The platform entry point. Every request names a user; each user has
    their own agent state (AgentRuntime), loaded from the backend on first
    use and saved back shortly after anything changes. Nothing is shared
    between users except the model chain and capability definitions."""

    def __init__(
        self,
        llm: ResilientLLM,
        backend: StateBackend,
        *,
        save_delay: float = 0.5,
        runtime_factory: Callable[..., AgentRuntime] = AgentRuntime,
        **runtime_options: Any,
    ):
        self.llm = llm
        self.backend = backend
        self.save_delay = save_delay
        self._factory = runtime_factory
        self._options = runtime_options
        self._agents: dict[str, AgentRuntime] = {}
        self._loading: dict[str, asyncio.Lock] = {}
        self._save_tasks: dict[str, asyncio.Task] = {}

    # --- agents -----------------------------------------------------------------

    async def agent(self, user_id: str) -> AgentRuntime:
        """The user's agent, loading saved state the first time it is used."""
        if user_id in self._agents:
            return self._agents[user_id]
        lock = self._loading.setdefault(user_id, asyncio.Lock())
        async with lock:
            if user_id not in self._agents:
                runtime = self._factory(self.llm, user_id=user_id, **self._options)
                saved = await self.backend.load(user_id)
                if saved is not None:
                    apply_snapshot(runtime, saved)
                runtime.on_change = lambda: self._schedule_save(user_id)
                self._agents[user_id] = runtime
        return self._agents[user_id]

    @property
    def loaded_users(self) -> list[str]:
        return sorted(self._agents)

    def set_model_chain(self, routes: list[ModelRoute], retries: int, base_delay: float) -> None:
        """Switch every user's agent to a new model chain (it is platform-wide)
        and refresh their open views."""
        self.llm.routes = routes
        self.llm.retries = max(retries, 0)
        self.llm.base_delay = max(base_delay, 0.0)
        for runtime in self._agents.values():
            for watcher in list(runtime.watchers):
                watcher()

    # --- requests ---------------------------------------------------------------

    async def submit(self, user_id: str, event: InputEvent) -> ReasoningSession:
        return (await self.agent(user_id)).submit(event)

    async def run(self, user_id: str, event: InputEvent) -> ReasoningSession:
        return await (await self.agent(user_id)).run(event)

    async def answer(self, user_id: str, response: Answer) -> bool:
        return (await self.agent(user_id)).answer(response)

    async def clear(self, user_id: str) -> None:
        runtime = await self.agent(user_id)
        await runtime.clear()
        await self.save(user_id)

    # --- download / restore -----------------------------------------------------

    async def export_state(self, user_id: str) -> dict[str, Any]:
        """The user's whole agent state, for download."""
        return take_snapshot(await self.agent(user_id))

    async def restore_state(self, user_id: str, data: dict[str, Any]) -> None:
        """Replace the user's agent state with a downloaded one. Running
        sessions for this user are stopped first. A state exported by one
        user id can be restored under another."""
        validate_snapshot(data)
        runtime = await self.agent(user_id)
        runtime.on_change = None
        await runtime.clear()
        apply_snapshot(runtime, data)
        runtime.on_change = lambda: self._schedule_save(user_id)
        await self.save(user_id)

    # --- durability -------------------------------------------------------------

    def _schedule_save(self, user_id: str) -> None:
        task = self._save_tasks.get(user_id)
        if task is None or task.done():
            self._save_tasks[user_id] = asyncio.get_running_loop().create_task(self._save_later(user_id))

    async def _save_later(self, user_id: str) -> None:
        await asyncio.sleep(self.save_delay)
        try:
            await self.save(user_id)
        except Exception:
            log.exception("saving agent state for %s failed", user_id)

    async def save(self, user_id: str) -> None:
        runtime = self._agents.get(user_id)
        if runtime is not None:
            await self.backend.save(user_id, take_snapshot(runtime))

    async def unload(self, user_id: str) -> None:
        """Save and drop a user's agent from memory (stopping its loops)."""
        runtime = self._agents.pop(user_id, None)
        if runtime is None:
            return
        runtime.on_change = None
        pending = self._save_tasks.pop(user_id, None)
        if pending:
            pending.cancel()
        snapshot = take_snapshot(runtime)
        runtime.ambient.stop_all()
        runtime.questions.cancel_all()
        await runtime.cancel_tasks()
        await self.backend.save(user_id, snapshot)

    async def shutdown(self) -> None:
        """Save every loaded agent and stop. Sessions still running are
        recorded as interrupted when the state is next loaded."""
        for user_id in list(self._agents):
            await self.unload(user_id)
