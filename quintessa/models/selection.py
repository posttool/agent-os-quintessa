from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Selection:
    """One option the user picked in a multi-select field, and how many."""

    option: str
    quantity: int = 1
