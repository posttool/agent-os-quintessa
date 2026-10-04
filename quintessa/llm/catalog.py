"""The models the web app's model picker offers, grouped by provider. Any
other `provider:model` still works when typed in by hand."""

from __future__ import annotations

import os
from typing import Any

MODELS: dict[str, list[tuple[str, str]]] = {
    "claude": [
        ("claude-opus-5-5", "Claude Opus 5.5"),
        ("claude-sonnet-5-5", "Claude Sonnet 5.5"),
        ("claude-fable-5-1", "Claude Fable 5.1"),
        ("claude-opus-5", "Claude Opus 5"),
        ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    ],
    "gemini": [
        ("gemini-3.8-flash", "Gemini 3.8 Flash"),
        ("gemini-2.5-pro", "Gemini 2.5 Pro"),
        ("gemini-2.5-flash", "Gemini 2.5 Flash"),
        ("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
    ],
}

PROVIDER_LABELS = {"claude": "Claude", "gemini": "Gemini (Vertex)"}


def provider_setup(provider: str) -> str:
    """What is missing before this provider can answer, or "" when it looks configured."""
    vertex = any(
        os.environ.get(v) for v in ("GOOGLE_CLOUD_PROJECT", "QUINTESSA_GCP_SA_JSON", "GOOGLE_APPLICATION_CREDENTIALS")
    )
    if provider == "gemini":
        return "" if vertex else "set GOOGLE_CLOUD_PROJECT or QUINTESSA_GCP_SA_JSON"
    if provider == "claude":
        if os.environ.get("QUINTESSA_CLAUDE_ON_VERTEX") == "1":
            return "" if vertex else "set GOOGLE_CLOUD_PROJECT or QUINTESSA_GCP_SA_JSON"
        keyed = os.environ.get("QUINTESSA_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        return "" if keyed else "set QUINTESSA_ANTHROPIC_API_KEY"
    return ""


def model_catalog() -> list[dict[str, Any]]:
    return [
        {
            "provider": provider,
            "label": PROVIDER_LABELS.get(provider, provider),
            "setup": provider_setup(provider),
            "models": [{"id": f"{provider}:{model}", "label": label} for model, label in models],
        }
        for provider, models in MODELS.items()
    ]
