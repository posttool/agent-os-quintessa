from __future__ import annotations

import json
from typing import Any

from google import genai
from google.auth.exceptions import GoogleAuthError
from google.genai import errors, types

from quintessa.llm.errors import FatalLLMError, InvalidOutputError, RefusalError, RetryableLLMError

_BLOCKED = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


class GeminiVertexAdapter:
    """Gemini through Vertex AI (application default credentials).
    JSON comes back via response_json_schema."""

    provider = "gemini"

    def __init__(self, client: Any | None = None, *, project: str | None = None, location: str = "global"):
        if client is None:
            try:
                client = genai.Client(vertexai=True, project=project, location=location)
            except GoogleAuthError as e:
                raise FatalLLMError(
                    "Vertex AI credentials not found: run `gcloud auth application-default login` "
                    "and set GOOGLE_CLOUD_PROJECT"
                ) from e
        self.client = client

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
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            max_output_tokens=max_tokens,
        )
        try:
            response = await self.client.aio.models.generate_content(model=model, contents=prompt, config=config)
        except errors.APIError as e:
            if e.code == 429 or (e.code or 0) >= 500:
                raise RetryableLLMError(f"gemini {model}: {e.code}") from e
            raise FatalLLMError(f"gemini {model}: {e.code} {e.message}") from e
        except GoogleAuthError as e:
            raise FatalLLMError(f"gemini {model}: Vertex credentials missing or invalid ({e})") from e
        except (TimeoutError, ConnectionError) as e:
            raise RetryableLLMError(f"gemini {model}: {e}") from e

        candidates = response.candidates or []
        reason = candidates[0].finish_reason if candidates else None
        reason_name = getattr(reason, "name", str(reason or ""))
        if not candidates or reason_name in _BLOCKED:
            raise RefusalError(f"gemini {model} blocked ({reason_name or 'no candidates'})")
        if reason_name == "MAX_TOKENS":
            raise InvalidOutputError(f"gemini {model} hit max tokens")
        text = response.text
        if not text:
            raise InvalidOutputError(f"gemini {model} returned no text")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise InvalidOutputError(f"gemini {model}: invalid JSON") from e
        if not isinstance(data, dict):
            raise InvalidOutputError(f"gemini {model}: expected a JSON object")
        return data
