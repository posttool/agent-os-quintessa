from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from quintessa.models import AmbientSource, InputEvent, InputKind, Subscription

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime


class AmbientBus:
    """Simulated streaming inputs. Sources emit events into the runtime at
    their own rate; process subscriptions emit progress for long-running
    tool calls until the last stage, then archive themselves.

    Global emission is on by default, with no sources."""

    def __init__(
        self,
        runtime: AgentRuntime,
        *,
        process_interval: float = 5.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.runtime = runtime
        self.enabled = True
        self.process_interval = process_interval
        self.sources: dict[str, AmbientSource] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._sleep = sleep

    # --- sources ------------------------------------------------------------

    def add_source(self, source: AmbientSource) -> None:
        self.sources[source.id] = source
        self._tasks[source.id] = asyncio.create_task(self._run_source(source))
        self.runtime.notify_changed()

    def remove_source(self, source_id: str) -> None:
        self.sources.pop(source_id, None)
        task = self._tasks.pop(source_id, None)
        if task:
            task.cancel()
        self.runtime.notify_changed()

    def set_speed(self, source_id: str, speed: float) -> None:
        self.sources[source_id].speed = speed
        self.runtime.notify_changed()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.runtime.notify_changed()

    def source_done(self, source_id: str) -> bool:
        task = self._tasks.get(source_id)
        return task is None or task.done()

    async def _run_source(self, source: AmbientSource) -> None:
        while True:
            for content in source.events:
                await self._sleep(source.interval_seconds / max(source.speed, 0.01))
                if self.enabled and source.enabled:
                    self.runtime.submit(
                        InputEvent(
                            source.kind,
                            content,
                            source=f"ambient:{source.name}",
                            device=source.device,
                            sender=source.sender,
                        )
                    )
            if not source.loop:
                return

    # --- long-running processes ------------------------------------------------

    def follow(self, subscription: Subscription) -> None:
        self._tasks[subscription.id] = asyncio.create_task(self._run_subscription(subscription))

    async def _run_subscription(self, subscription: Subscription) -> None:
        while not subscription.complete and not subscription.archived:
            await self._sleep(self.process_interval)
            stage = subscription.stages[subscription.next_stage]
            subscription.next_stage += 1
            final = subscription.complete
            if final:
                subscription.archived = True
            self.runtime.store.put_subscription(subscription)
            if self.enabled:
                content = (
                    f"{subscription.description} | stage {subscription.next_stage}/{len(subscription.stages)}: {stage}"
                )
                if final:
                    content += " | process complete"
                self.runtime.submit(
                    InputEvent(
                        InputKind.PROCESS_PROGRESS,
                        content,
                        source=f"process:{subscription.tool}",
                        subscription_id=subscription.id,
                    )
                )

    # --- lifecycle -------------------------------------------------------------

    def stop_all(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        self.sources.clear()
