"""Generic dataclass <-> plain dict conversion, used for persistence and for
handing structured context to the LLM. This is structural mapping only; it
never interprets content."""

from __future__ import annotations

import dataclasses
import enum
import types
import typing
from datetime import datetime
from functools import lru_cache
from typing import Any, TypeVar

T = TypeVar("T")


def to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_dict(v) for v in obj]
    return obj


@lru_cache(maxsize=None)
def _hints(cls: type) -> dict[str, Any]:
    return typing.get_type_hints(cls)


def from_dict(cls: type[T], data: Any) -> T:
    return _convert(cls, data)


def _convert(tp: Any, value: Any) -> Any:
    if value is None:
        return None
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (typing.Union, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        return _convert(non_none[0], value) if len(non_none) == 1 else value
    if origin in (list, tuple, set):
        inner = args[0] if args else Any
        return [_convert(inner, v) for v in value]
    if origin is dict:
        vt = args[1] if len(args) == 2 else Any
        return {k: _convert(vt, v) for k, v in value.items()}
    if tp is Any:
        return value
    if isinstance(tp, type):
        if dataclasses.is_dataclass(tp):
            hints = _hints(tp)
            kwargs = {
                f.name: _convert(hints[f.name], value[f.name])
                for f in dataclasses.fields(tp)
                if f.name in value and f.init
            }
            return tp(**kwargs)
        if issubclass(tp, enum.Enum):
            return tp(value)
        if tp is datetime:
            return value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return value
