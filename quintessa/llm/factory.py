from __future__ import annotations

from quintessa import config
from quintessa.llm.client import LLMClient
from quintessa.llm.credentials import load_service_account_env
from quintessa.llm.resilient import ModelRoute, ResilientLLM

DEFAULT_CHAIN = "gemini:gemini-3.8-flash,gemini:gemini-2.5-flash"


def build_llm(chain: str | None = None) -> ResilientLLM:
    """Build the model chain from `provider:model` pairs, e.g.
    "gemini:gemini-3.8-flash,gemini:gemini-2.5-flash,claude:claude-opus-5-5".

    Environment:
      QUINTESSA_MODEL_CHAIN     the chain (default: Gemini 3.8 Flash, then 2.5 Flash)
      QUINTESSA_LLM_RETRIES     retries per model (default 2)
      GOOGLE_CLOUD_PROJECT      Vertex project for Gemini (and Claude on Vertex)
      QUINTESSA_GCP_SA_JSON     a service account key's JSON, used when no credentials file is set
      GOOGLE_CLOUD_LOCATION     Vertex location (default "global")
      QUINTESSA_CLAUDE_ON_VERTEX=1   send Claude through Vertex instead of the Anthropic API
      QUINTESSA_ANTHROPIC_API_KEY   Anthropic API credential when not on Vertex
      ANTHROPIC_API_KEY         used when QUINTESSA_ANTHROPIC_API_KEY is not set
    """
    load_service_account_env()
    spec = chain or config.model_chain(DEFAULT_CHAIN)
    clients: dict[str, LLMClient] = {}
    routes = []
    for item in [s.strip() for s in spec.split(",") if s.strip()]:
        provider, _, model = item.partition(":")
        if provider not in clients:
            clients[provider] = _client_for(provider)
        routes.append(ModelRoute(clients[provider], model))
    return ResilientLLM(routes, retries=config.llm_retries())


def _client_for(provider: str) -> LLMClient:
    project = config.gcp_project()
    location = config.gcp_location()
    if provider == "gemini":
        from quintessa.llm.gemini_vertex import GeminiVertexAdapter

        return GeminiVertexAdapter(project=project, location=location)
    if provider == "claude":
        from quintessa.llm.claude import ClaudeAdapter

        on_vertex = config.claude_on_vertex()
        return ClaudeAdapter(vertex_project=project if on_vertex else None, vertex_region=location)
    raise ValueError(f"unknown LLM provider {provider!r}")
