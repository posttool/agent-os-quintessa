from __future__ import annotations

from typing import Any, Protocol


class SearchBackend(Protocol):
    async def search(self, query: str) -> str: ...


class GeminiGroundedSearch:
    """Google Search through Gemini's search grounding on Vertex AI."""

    def __init__(self, client: Any | None = None, *, project: str | None = None, location: str = "global",
                 model: str = "gemini-3.8-flash"):
        from google import genai

        self.client = client or genai.Client(vertexai=True, project=project, location=location)
        self.model = model

    async def search(self, query: str) -> str:
        from google.genai import types

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=f"Search the web and report what you find, with source URLs: {query}",
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
        )
        return response.text or ""
