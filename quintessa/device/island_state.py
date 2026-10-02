from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IslandState:
    """The dynamic island: pulses while the agent works, with a word or two."""

    active: bool = False
    words: str = ""
