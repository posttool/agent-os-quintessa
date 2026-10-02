from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PersonaProfile:
    """A simulated user from the Aura persona service (posttool/persona)."""

    id: str
    name: str
    occupation: str = ""
    city: str = ""
    age: Any = None
    hobbies: Any = None
    goals_this_week: Any = None
    family: Any = None
    apps: Any = None
    image: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
