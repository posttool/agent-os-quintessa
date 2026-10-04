from __future__ import annotations

from typing import Any, Protocol

from quintessa import config
from quintessa.prompts import prompt


class SearchBackend(Protocol):
    async def search(self, query: str) -> str: ...


class GeminiGroundedSearch:
    """Google Search through Gemini's search grounding on Vertex AI."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        project: str | None = None,
        location: str = "global",
        model: str = "gemini-3.8-flash",
    ):
        from google import genai

        self.client = client or genai.Client(vertexai=True, project=project, location=location)
        self.model = model

    async def search(self, query: str) -> str:
        from google.genai import types

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt("web_search", query=query),
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
        )
        return response.text or ""


class ClaudeWebSearch:
    """Web search through Claude's server-side web_search tool on the Anthropic API."""

    TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}

    def __init__(self, client: Any | None = None, *, model: str = "claude-opus-5-5", max_continuations: int = 3):
        if client is None:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key())
        self.client = client
        self.model = model
        self.max_continuations = max_continuations

    async def search(self, query: str) -> str:
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt("web_search", query=query)}]
        for _ in range(self.max_continuations + 1):
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=16000,
                messages=messages,
                tools=[self.TOOL],
                output_config={"effort": "low"},
            )
            if response.stop_reason != "pause_turn":
                break
            # A long search pauses mid-turn; send the partial turn back to let it finish.
            messages = [messages[0], {"role": "assistant", "content": response.content}]
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        urls = dict.fromkeys(
            c.url for b in response.content if b.type == "text" for c in (b.citations or []) if getattr(c, "url", None)
        )
        if urls:
            text += "\n\nSources:\n" + "\n".join(urls)
        return text


def search_backend_from_env() -> SearchBackend | None:
    """Gemini's Google Search grounding when GOOGLE_CLOUD_PROJECT is set,
    otherwise Claude's web search when an Anthropic key is set."""
    if config.gcp_project():
        return GeminiGroundedSearch(project=config.gcp_project(), location=config.gcp_location())
    if config.anthropic_api_key():
        return ClaudeWebSearch(model=config.search_model())
    return None
