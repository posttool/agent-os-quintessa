from __future__ import annotations

from dataclasses import dataclass, field

from quintessa.models.field_kind import FieldKind


@dataclass
class QuestionField:
    """A design-system-agnostic form element. Skins decide how to draw it."""

    name: str
    kind: FieldKind
    label: str = ""
    options: list[str] = field(default_factory=list)
