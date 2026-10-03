from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ShadowDecision:
    """What a System One model (Jev, gev) would have chosen at one decision
    point, recorded beside what the LLM chose. It never steers the loop.
    `step_index` is the step being decided; the decision that ends a session
    has the index one past the last step, with `llm_choice` "done".
    When the user lets Jev drive, `drove` is set: its choice was followed
    and no LLM was asked (`llm_choice` stays empty)."""

    step_index: int
    llm_choice: str
    choice: str = ""
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    model: str = ""
    latency_ms: float = 0.0
    error: str = ""
    drove: bool = False

    @property
    def agrees(self) -> bool:
        return not self.error and not self.drove and self.choice == self.llm_choice
