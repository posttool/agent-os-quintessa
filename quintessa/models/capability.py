from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Capability:
    """A reasoning capability, loaded from a markdown file. `instructions` is
    the file body; `executor` names the code that applies its output.
    `choose_when` describes the situations that call for it, for decision
    models that pick the next step from criteria."""

    name: str
    description: str
    executor: str
    instructions: str
    source_path: str = ""
    choose_when: str = ""
