from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str = ""
    required: bool = True
