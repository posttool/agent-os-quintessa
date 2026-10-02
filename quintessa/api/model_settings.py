from __future__ import annotations

from dataclasses import dataclass, field

from quintessa.llm.factory import DEFAULT_CHAIN


@dataclass
class ModelSettings:
    """Platform-wide model chain and the retry / fallback strategy."""

    chain: list[str] = field(default_factory=lambda: DEFAULT_CHAIN.split(","))
    retries: int = 2
    base_delay: float = 1.0
    status: str = ""
