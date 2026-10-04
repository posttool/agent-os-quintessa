from __future__ import annotations

from dataclasses import dataclass

# The controller's choice that ends a session; StepDecision stores it as capability "".
DONE = "done"


@dataclass
class StepDecision:
    """The loop's choice of what to do next. capability == "" means done.
    `status_words` are shown in the dynamic island, `model` is the model that
    chose, and `decided_by` is "jev" when Jev chose, "" for the LLM."""

    capability: str
    focus: str
    rationale: str
    status_words: str = ""
    model: str = ""
    decided_by: str = ""
