from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Capability:
    """A reasoning capability, loaded from a markdown file. `instructions` is
    the file body; `executor` names the code that applies its output."""

    name: str
    description: str
    executor: str
    instructions: str
    source_path: str = ""
