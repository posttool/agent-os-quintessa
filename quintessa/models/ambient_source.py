from __future__ import annotations

from dataclasses import dataclass, field

from quintessa.clock import new_id
from quintessa.models.input_kind import InputKind


@dataclass
class AmbientSource:
    """A simulated stream of incoming data (emails, SMS, location, a drive to
    work). `events` are emitted in order at `interval_seconds` / speed."""

    name: str
    kind: InputKind
    events: list[str] = field(default_factory=list)
    interval_seconds: float = 5.0
    speed: float = 1.0
    enabled: bool = True
    loop: bool = False
    device: str = "phone"
    sender: str = ""
    id: str = field(default_factory=lambda: new_id("src"))
