from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResult:
    data: dict[str, Any]
    model: str
    provider: str
    attempts: int = 1
