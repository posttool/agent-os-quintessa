from __future__ import annotations

from dataclasses import dataclass, field

from quintessa.device.brief_item import BriefItem
from quintessa.device.discovery_item import DiscoveryItem
from quintessa.device.island_state import IslandState


@dataclass
class DeviceState:
    """What the experience surfaces show. Skins render this; they never reach
    into memory directly."""

    island: IslandState = field(default_factory=IslandState)
    brief: list[BriefItem] = field(default_factory=list)
    open_ux_ids: list[str] = field(default_factory=list)
    space_document_ids: list[str] = field(default_factory=list)
    focused_document_id: str | None = None
    focused_section_id: str | None = None
    discovery: list[DiscoveryItem] = field(default_factory=list)
    notifications: list[str] = field(default_factory=list)
