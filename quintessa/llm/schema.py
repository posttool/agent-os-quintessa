"""Small helpers for writing JSON schemas that both Claude structured outputs
and Gemini response schemas accept (every object closed, every property
required, optional values expressed as nullable)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from quintessa.llm.errors import InvalidOutputError


def string(description: str = "") -> dict[str, Any]:
    return _desc({"type": "string"}, description)


def number(description: str = "") -> dict[str, Any]:
    return _desc({"type": "number"}, description)


def boolean(description: str = "") -> dict[str, Any]:
    return _desc({"type": "boolean"}, description)


def enum_of(values: type[Enum] | list[str], description: str = "") -> dict[str, Any]:
    vals = [v.value for v in values] if isinstance(values, type) else list(values)
    return _desc({"type": "string", "enum": vals}, description)


def array(items: dict[str, Any], description: str = "") -> dict[str, Any]:
    return _desc({"type": "array", "items": items}, description)


def obj(properties: dict[str, dict[str, Any]], description: str = "") -> dict[str, Any]:
    return _desc(
        {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
        description,
    )


def nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _desc(schema: dict[str, Any], description: str) -> dict[str, Any]:
    if description:
        schema["description"] = description
    return schema


_TYPES = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def validate(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Structural check of model output against the schema subset above."""
    if "anyOf" in schema:
        errors = []
        for option in schema["anyOf"]:
            try:
                validate(value, option, path)
                return
            except InvalidOutputError as e:
                errors.append(str(e))
        raise InvalidOutputError(f"{path}: matched no option ({'; '.join(errors)})")
    expected = schema.get("type")
    if expected:
        py = _TYPES[expected]
        if not isinstance(value, py) or (expected in ("number", "integer") and isinstance(value, bool)):
            raise InvalidOutputError(f"{path}: expected {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise InvalidOutputError(f"{path}: {value!r} not in {schema['enum']}")
    if expected == "object":
        for key in schema.get("required", []):
            if key not in value:
                raise InvalidOutputError(f"{path}: missing {key}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                validate(value[key], sub, f"{path}.{key}")
    if expected == "array":
        for i, item in enumerate(value):
            validate(item, schema["items"], f"{path}[{i}]")
