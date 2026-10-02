from __future__ import annotations

import os

from quintessa.llm.client import LLMClient
from quintessa.llm.resilient import ModelRoute, ResilientLLM

DEFAULT_CHAIN = "gemini:gemini-3.8-flash,gemini:gemini-2.5-flash"


def build_llm(chain: str | None = None) -> ResilientLLM:
    """Build the model chain from `provider:model` pairs, e.g.
    "gemini:gemini-3.8-flash,gemini:gemini-2.5-flash,claude:claude-opus-5-5".

    Environment:
      QUINTESSA_MODEL_CHAIN     the chain (default: Gemini 3.8 Flash, then 2.5 Flash)
      QUINTESSA_LLM_RETRIES     retries per model (default 2)
      GOOGLE_CLOUD_PROJECT      Vertex project for Gemini (and Claude on Vertex)
      GOOGLE_CLOUD_LOCATION     Vertex location (default "global")
      QUINTESSA_CLAUDE_ON_VERTEX=1   send Claude through Vertex instead of the Anthropic API
      QUINTESSA_ANTHROPIC_API_KEY   Anthropic API credential when not on Vertex
      ANTHROPIC_API_KEY         used when QUINTESSA_ANTHROPIC_API_KEY is not set
    """
    spec = chain or os.environ.get("QUINTESSA_MODEL_CHAIN", DEFAULT_CHAIN)
    clients: dict[str, LLMClient] = {}
    routes = []
    for item in [s.strip() for s in spec.split(",") if s.strip()]:
        provider, _, model = item.partition(":")
        if provider not in clients:
            clients[provider] = _client_for(provider)
        routes.append(ModelRoute(clients[provider], model))
    return ResilientLLM(routes, retries=int(os.environ.get("QUINTESSA_LLM_RETRIES", "2")))


def _client_for(provider: str) -> LLMClient:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    if provider == "gemini":
        from quintessa.llm.gemini_vertex import GeminiVertexAdapter

        return GeminiVertexAdapter(project=project, location=location)
    if provider == "claude":
        from quintessa.llm.claude import ClaudeAdapter

        on_vertex = os.environ.get("QUINTESSA_CLAUDE_ON_VERTEX") == "1"
        return ClaudeAdapter(vertex_project=project if on_vertex else None, vertex_region=location)
    raise ValueError(f"unknown LLM provider {provider!r}")
