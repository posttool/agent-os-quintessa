"""The schema a model writes tool functions in, shared by tool discovery
and app installs, and turning that output into ToolFunctions."""

from __future__ import annotations

from typing import Any

from quintessa.llm import schema as s
from quintessa.models import OversightLevel, ToolFunction, ToolParameter

FUNCTION_SCHEMA = s.obj(
    {
        "name": s.string(),
        "description": s.string(),
        "parameters": s.array(
            s.obj(
                {
                    "name": s.string(),
                    "type": s.string(),
                    "description": s.string(),
                    "required": s.boolean(),
                }
            )
        ),
        "returns": s.string(),
        "oversight": s.enum_of(OversightLevel),
        "long_running": s.boolean(),
    }
)


def functions_from(data: list[dict[str, Any]]) -> list[ToolFunction]:
    return [
        ToolFunction(
            f["name"],
            f["description"],
            [ToolParameter(p["name"], p["type"], p["description"], p["required"]) for p in f["parameters"]],
            f["returns"],
            OversightLevel(f["oversight"]),
            f["long_running"],
        )
        for f in data
    ]
