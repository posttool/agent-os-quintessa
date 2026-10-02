from __future__ import annotations

from dataclasses import dataclass, field

from quintessa.models.ux_field_kind import UXFieldKind


@dataclass
class UXField:
    """A design-system-agnostic form element. Skins decide how to draw it."""

    name: str
    kind: UXFieldKind
    label: str = ""
    options: list[str] = field(default_factory=list)
