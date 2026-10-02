from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from quintessa.llm.client import LLMClient
from quintessa.llm.errors import (
    FatalLLMError,
    InvalidOutputError,
    LLMUnavailableError,
    RefusalError,
    RetryableLLMError,
)
from quintessa.llm.result import LLMResult
from quintessa.llm.schema import validate

log = logging.getLogger(__name__)


@dataclass
class ModelRoute:
    client: LLMClient
    model: str

    @property
    def label(self) -> str:
        return f"{self.client.provider}:{self.model}"


class ResilientLLM:
    """Tries each route in order. Transient failures and malformed output are
    retried with exponential backoff on the same model; refusals and hard
    errors fall back to the next (older) model."""

    def __init__(
        self,
        routes: list[ModelRoute],
        *,
        retries: int = 2,
        base_delay: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if not routes:
            raise ValueError("at least one model route is required")
        self.routes = routes
        self.retries = retries
        self.base_delay = base_delay
        self._sleep = sleep

    async def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 8000,
        purpose: str = "",
    ) -> LLMResult:
        failures: list[str] = []
        attempts = 0
        for route in list(self.routes):
            for attempt in range(self.retries + 1):
                attempts += 1
                try:
                    data = await route.client.generate_json(
                        model=route.model,
                        system=system,
                        prompt=prompt,
                        schema=schema,
                        max_tokens=max_tokens,
                        purpose=purpose,
                    )
                    validate(data, schema)
                    return LLMResult(data=data, model=route.model, provider=route.client.provider, attempts=attempts)
                except (RetryableLLMError, InvalidOutputError) as e:
                    failures.append(f"{route.label}: {e}")
                    log.warning("LLM attempt failed (%s), attempt %d", e, attempt + 1)
                    if attempt < self.retries:
                        await self._sleep(self.base_delay * (2**attempt))
                except (RefusalError, FatalLLMError) as e:
                    failures.append(f"{route.label}: {e}")
                    log.warning("LLM route %s failed, falling back: %s", route.label, e)
                    break
        raise LLMUnavailableError(failures)
