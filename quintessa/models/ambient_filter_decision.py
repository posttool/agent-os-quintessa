from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AmbientFilterDecision:
    """A System One model's answer to "does this ambient event matter?",
    asked before a session spends any LLM calls. `matters` is P(yes); below
    the threshold the session ends at once with no steps. A failed call
    never skips: `error` is set and the session runs as usual."""

    matters: float
    threshold: float
    skipped: bool
    model: str = ""
    latency_ms: float = 0.0
    error: str = ""
