from __future__ import annotations

import json
from typing import Any

from quintessa.llm.errors import InvalidOutputError


def json_object(text: str | None, who: str) -> dict[str, Any]:
    """The model's reply as a JSON object, or InvalidOutputError naming `who`
    (e.g. "claude claude-opus-5-5")."""
    if not text:
        raise InvalidOutputError(f"{who} returned no text")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise InvalidOutputError(f"{who}: invalid JSON") from e
    if not isinstance(data, dict):
        raise InvalidOutputError(f"{who}: expected a JSON object")
    return data
