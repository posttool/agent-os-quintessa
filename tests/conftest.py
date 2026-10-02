from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, Callable

import pytest

from quintessa.llm import ModelRoute, ResilientLLM, ScriptedLLM
from quintessa.loop import AgentRuntime


async def no_sleep(_: float) -> None:
    await asyncio.sleep(0)


def decide(capability: str, focus: str = "", words: str = "Working") -> dict[str, Any]:
    return {"capability": capability, "focus": focus or capability, "rationale": "test", "status_words": words}


DONE = decide("done")


class Script:
    """Answers model calls by purpose ("decide", "capability:memory",
    "tool:food_delivery.checkout", ...) from queued responses. Each queued
    item is a dict, an LLMError, or a function of the prompt payload.
    Unscripted "decide" calls answer done."""

    def __init__(self) -> None:
        self.queues: dict[str, list[Any]] = defaultdict(list)
        self.prompts: dict[str, list[dict]] = defaultdict(list)

    def on(self, purpose: str, *answers: Any) -> "Script":
        self.queues[purpose].extend(answers)
        return self

    def __call__(self, purpose: str, system: str, prompt: str, schema: dict) -> Any:
        payload = json.loads(prompt)
        self.prompts[purpose].append(payload)
        queue = self.queues[purpose]
        if not queue:
            if purpose == "decide":
                return DONE
            raise AssertionError(f"unscripted model call: {purpose}")
        answer = queue.pop(0)
        return answer(payload) if isinstance(answer, Callable) else answer


@pytest.fixture
def script() -> Script:
    return Script()


@pytest.fixture
def make_runtime(tmp_path) -> Callable[..., AgentRuntime]:
    def build(script: Script, **kwargs: Any) -> AgentRuntime:
        llm = ResilientLLM([ModelRoute(ScriptedLLM(script), "test-model")], retries=0, sleep=no_sleep)
        kwargs.setdefault("process_interval", 0)
        return AgentRuntime(llm, data_dir=tmp_path, sleep=no_sleep, **kwargs)

    return build


@pytest.fixture
def make_host(tmp_path) -> Callable[..., Any]:
    from quintessa.host import AgentHost

    def build(script: Script, backend: Any, **kwargs: Any) -> AgentHost:
        llm = ResilientLLM([ModelRoute(ScriptedLLM(script), "test-model")], retries=0, sleep=no_sleep)
        kwargs.setdefault("process_interval", 0)
        kwargs.setdefault("save_delay", 0)
        return AgentHost(llm, backend, data_dir=tmp_path, sleep=no_sleep, **kwargs)

    return build


async def until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.001)

    await asyncio.wait_for(poll(), timeout)
