"""The models the web app's model picker offers, grouped by provider. Any
other `provider:model` still works when typed in by hand."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from quintessa import config


def providers() -> dict[str, Any]:
    """The picker's models, from quintessa/samples/models.json."""
    return json.loads(resources.files("quintessa.samples").joinpath("models.json").read_text())


def provider_setup(provider: str) -> str:
    """What is missing before this provider can answer, or "" when it looks configured."""
    vertex = config.vertex_configured()
    if provider == "gemini":
        return "" if vertex else "set GOOGLE_CLOUD_PROJECT or QUINTESSA_GCP_SA_JSON"
    if provider == "claude":
        if config.claude_on_vertex():
            return "" if vertex else "set GOOGLE_CLOUD_PROJECT or QUINTESSA_GCP_SA_JSON"
        keyed = config.anthropic_api_key()
        return "" if keyed else "set QUINTESSA_ANTHROPIC_API_KEY"
    return ""


def model_catalog() -> list[dict[str, Any]]:
    return [
        {
            "provider": provider,
            "label": entry["label"],
            "setup": provider_setup(provider),
            "models": [{"id": f"{provider}:{m['id']}", "label": m["label"]} for m in entry["models"]],
        }
        for provider, entry in providers().items()
    ]
