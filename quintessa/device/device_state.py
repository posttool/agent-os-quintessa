from __future__ import annotations

from dataclasses import dataclass, field

from quintessa.device.card import Card
from quintessa.device.discovery_item import DiscoveryItem
from quintessa.device.document_focus import DocumentFocus
from quintessa.device.island_state import IslandState
from quintessa.device.salience import Suppression
from quintessa.device.stashed_question import StashedQuestion


@dataclass
class DeviceState:
    """What the experience surfaces show. Skins render this; they never reach
    into memory directly."""

    island: IslandState = field(default_factory=IslandState)
    brief: list[Card] = field(default_factory=list)  # highest salience first
    snoozed: list[Card] = field(default_factory=list)  # back in the brief at their snoozed_until
    suppressions: list[Suppression] = field(default_factory=list)
    open_question_ids: list[str] = field(default_factory=list)
    stashed: list[StashedQuestion] = field(default_factory=list)  # questions put aside, still waiting
    space_document_ids: list[str] = field(default_factory=list)
    focused_document_id: str | None = None
    focus: dict[str, DocumentFocus] = field(default_factory=dict)
    discovery: list[DiscoveryItem] = field(default_factory=list)
    notifications: list[str] = field(default_factory=list)
