from __future__ import annotations

from typing import Any, Callable

from quintessa.llm.errors import LLMError

Responder = Callable[[str, str, str, dict[str, Any]], "dict[str, Any] | LLMError"]


class ScriptedLLM:
    """A stand-in model for tests and offline demos. `responder` receives
    (purpose, system, prompt, schema) and returns the JSON to answer with,
    or an LLMError instance to raise."""

    def __init__(self, responder: Responder, provider: str = "scripted"):
        self.responder = responder
        self.provider = provider
        self.calls: list[dict[str, Any]] = []

    async def generate_json(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        purpose: str = "",
    ) -> dict[str, Any]:
        self.calls.append({"model": model, "purpose": purpose, "system": system, "prompt": prompt})
        answer = self.responder(purpose, system, prompt, schema)
        if isinstance(answer, LLMError):
            raise answer
        return answer
