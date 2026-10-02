from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KeyDate:
    when: str
    label: str
    tentative: bool = False
