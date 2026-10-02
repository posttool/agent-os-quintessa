from __future__ import annotations

from typing import Any

from quintessa.llm.errors import FatalLLMError


class UnconfiguredLLM:
    """Stands in when no model could be set up (missing credentials), so the
    platform still starts and every session fails with a clear reason."""

    provider = "unconfigured"

    def __init__(self, reason: str):
        self.reason = reason

    async def generate_json(self, **_: Any) -> dict[str, Any]:
        raise FatalLLMError(f"no model is configured: {self.reason}")
