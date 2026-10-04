"""Every setting Quintessa reads from the environment, in one place. Each
is read when asked for, not at import, so a changed variable (or a test's
monkeypatch) takes effect on the next call. The README's environment table
lists the same variables. (llm/credentials.py is the one writer: it turns
QUINTESSA_GCP_SA_JSON into the file Google's libraries look for.)"""

from __future__ import annotations

import os


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _flag(name: str) -> bool:
    return _get(name) == "1"


# Models


def model_chain(default: str) -> str:
    """QUINTESSA_MODEL_CHAIN: models tried in order, e.g. claude:claude-opus-5-5,gemini:gemini-3-pro."""
    return _get("QUINTESSA_MODEL_CHAIN", default)


def llm_retries() -> int:
    return int(_get("QUINTESSA_LLM_RETRIES", "2"))


def anthropic_api_key() -> str | None:
    """QUINTESSA_ANTHROPIC_API_KEY, else ANTHROPIC_API_KEY."""
    return _get("QUINTESSA_ANTHROPIC_API_KEY") or _get("ANTHROPIC_API_KEY") or None


def claude_on_vertex() -> bool:
    """QUINTESSA_CLAUDE_ON_VERTEX=1 sends Claude through Vertex instead of the Anthropic API."""
    return _flag("QUINTESSA_CLAUDE_ON_VERTEX")


def gcp_project() -> str | None:
    return _get("GOOGLE_CLOUD_PROJECT") or None


def gcp_location() -> str:
    return _get("GOOGLE_CLOUD_LOCATION", "global")


def vertex_configured() -> bool:
    """A project, a service-account key or a credentials file is set."""
    return any(_get(v) for v in ("GOOGLE_CLOUD_PROJECT", "QUINTESSA_GCP_SA_JSON", "GOOGLE_APPLICATION_CREDENTIALS"))


def search_model() -> str:
    return _get("QUINTESSA_SEARCH_MODEL", "claude-opus-5-5")


# Jev (System One)


def jev_api_key() -> str | None:
    """QUINTESSA_JEV_API_KEY, else TYPESAFE_API_KEY."""
    return _get("QUINTESSA_JEV_API_KEY") or _get("TYPESAFE_API_KEY") or None


def jev_url(default: str) -> str:
    return _get("QUINTESSA_JEV_URL", default)


def jev_model(default: str) -> str:
    return _get("QUINTESSA_JEV_MODEL", default)


def jev_shadow_default() -> bool:
    """Users start with Jev in shadow unless QUINTESSA_DECIDER=llm."""
    return _get("QUINTESSA_DECIDER", "shadow") != "llm"


def jev_filter_default() -> bool:
    """Users start with the ambient filter on when QUINTESSA_AMBIENT_FILTER=1."""
    return _flag("QUINTESSA_AMBIENT_FILTER")


def ambient_threshold(default: float) -> float:
    return float(_get("QUINTESSA_AMBIENT_THRESHOLD", str(default)))


# Tools and apps


def sim_failure_rate(default: float) -> float:
    """QUINTESSA_SIM_FAILURE_RATE, clamped to 0..1; the default when unreadable."""
    try:
        return min(max(float(_get("QUINTESSA_SIM_FAILURE_RATE", str(default))), 0.0), 1.0)
    except ValueError:
        return default


def app_store() -> str:
    """QUINTESSA_APP_STORE: play, search, offline or auto."""
    return _get("QUINTESSA_APP_STORE", "auto").lower()


def persona_base_url(default: str) -> str:
    return _get("AURA_PERSONA_BASE_URL", default)


# Storage and serving


def state_kind() -> str:
    """QUINTESSA_STATE=file keeps one JSON file per user; anything else uses the database."""
    return _get("QUINTESSA_STATE").lower()


def database_url() -> str | None:
    return _get("QUINTESSA_DATABASE_URL") or None


def web_dist(default: str) -> str:
    return _get("QUINTESSA_WEB_DIST", default)


def default_user() -> str:
    """QUINTESSA_USER: whose agent the CLI uses."""
    return _get("QUINTESSA_USER", "local")
