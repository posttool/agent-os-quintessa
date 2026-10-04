from __future__ import annotations

from dataclasses import dataclass

# The controller's choice that ends a session; StepDecision stores it as capability "".
DONE = "done"


@dataclass
class StepDecision:
    """The loop's choice of what to do next. capability == "" means done."""

    capability: str
    focus: str
    rationale: str
