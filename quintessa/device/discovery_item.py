from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiscoveryItem:
    title: str
    reason: str
    topic_id: str | None = None
