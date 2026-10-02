from __future__ import annotations

from dataclasses import dataclass

from quintessa.models.trigger_type import TriggerType


@dataclass
class TriggerSpec:
    """When a topic should surface, e.g. (LOCATION, "at the grocery store")
    or (TIME, "the day before the party"). `user_override` marks rules set by
    the user, which win over agent-reasoned defaults."""

    type: TriggerType
    condition: str
    reasoning: str = ""
    user_override: bool = False
