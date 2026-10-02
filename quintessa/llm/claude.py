from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from quintessa.llm.errors import FatalLLMError, InvalidOutputError, RefusalError, RetryableLLMError

# Models that accept the server-side refusal fallback ("fallbacks": "default").
SERVER_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeAdapter:
    """Claude through the Anthropic API, or through Vertex AI when
    `vertex_project` is set. JSON comes back via structured outputs."""

    provider = "claude"

    def __init__(
        self,
        client: Any | None = None,
        *,
        vertex_project: str | None = None,
        vertex_region: str = "global",
        effort: str = "medium",
        server_fallbacks: bool = True,
    ):
        if client is None:
            if vertex_project:
                client = anthropic.AsyncAnthropicVertex(project_id=vertex_project, region=vertex_region)
            else:
                # QUINTESSA_ANTHROPIC_API_KEY wins; with neither set the SDK reads ANTHROPIC_API_KEY.
                client = anthropic.AsyncAnthropic(api_key=os.environ.get("QUINTESSA_ANTHROPIC_API_KEY") or None)
        self.client = client
        self.effort = effort
        # The server-side fallback parameter is a Claude API feature; it is
        # not available on Vertex, where ResilientLLM's chain covers it.
        self.server_fallbacks = server_fallbacks and not vertex_project

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
        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
        )
        try:
            if self.server_fallbacks and model in SERVER_FALLBACK_MODELS:
                response = await self.client.beta.messages.create(
                    **kwargs, betas=[SERVER_FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = await self.client.messages.create(**kwargs)
        except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APITimeoutError) as e:
            raise RetryableLLMError(f"claude {model}: {e}") from e
        except anthropic.APIConnectionError as e:
            raise RetryableLLMError(f"claude {model}: connection error {e}") from e
        except anthropic.APIStatusError as e:
            if e.status_code == 429 or e.status_code >= 500:
                raise RetryableLLMError(f"claude {model}: {e.status_code}") from e
            raise FatalLLMError(f"claude {model}: {e.status_code} {e.message}") from e

        if response.stop_reason == "refusal":
            raise RefusalError(f"claude {model} declined")
        if response.stop_reason == "max_tokens":
            raise InvalidOutputError(f"claude {model} hit max_tokens")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise InvalidOutputError(f"claude {model} returned no text")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise InvalidOutputError(f"claude {model}: invalid JSON") from e
        if not isinstance(data, dict):
            raise InvalidOutputError(f"claude {model}: expected a JSON object")
        return data
