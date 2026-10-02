from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StepDecision:
    """The loop's choice of what to do next. capability == "" means done."""

    capability: str
    focus: str
    rationale: str
