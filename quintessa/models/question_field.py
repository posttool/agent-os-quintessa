from __future__ import annotations

from dataclasses import dataclass, field

from quintessa.models.field_kind import FieldKind
from quintessa.models.question_option import QuestionOption


@dataclass
class QuestionField:
    """A design-system-agnostic form element. Skins decide how to draw it."""

    name: str
    kind: FieldKind
    label: str = ""
    options: list[str] = field(default_factory=list)
    # pictures and quantities for some of the options, by option label
    option_details: list[QuestionOption] = field(default_factory=list)

    def detail(self, option: str) -> QuestionOption | None:
        return next((d for d in self.option_details if d.option == option), None)
