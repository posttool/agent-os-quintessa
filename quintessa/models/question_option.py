from __future__ import annotations

from dataclasses import dataclass

from quintessa.models.picture import Picture


@dataclass
class QuestionOption:
    """More about one option of a choice field: the picture a tool returned
    for it, and whether the user says how many when they pick it."""

    option: str
    picture: Picture | None = None
    takes_quantity: bool = False
