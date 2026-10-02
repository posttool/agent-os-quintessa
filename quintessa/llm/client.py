from __future__ import annotations

from typing import Any, Protocol


class LLMClient(Protocol):
    """A provider adapter. Every call returns a JSON object matching `schema`;
    reasoning happens in the model, never in string handling on our side."""

    provider: str

    async def generate_json(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        purpose: str,
    ) -> dict[str, Any]: ...
