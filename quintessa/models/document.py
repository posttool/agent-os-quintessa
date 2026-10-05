from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from quintessa.clock import now
from quintessa.models.document_section import DocumentSection
from quintessa.models.document_status import DocumentStatus
from quintessa.models.key_date import KeyDate
from quintessa.models.picture import Picture


@dataclass
class Document:
    """A progressively built record of a topic's lifecycle: sections, progress,
    live process status, key dates and relevant observations."""

    id: str
    title: str
    topic_id: str | None = None
    description: str = ""
    status: DocumentStatus = DocumentStatus.DRAFT
    progress_overview: str = ""
    sections: list[DocumentSection] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    key_dates: list[KeyDate] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    # good pictures of what the user chose in a question about this
    pictures: list[Picture] = field(default_factory=list)
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)

    @property
    def archived(self) -> bool:
        return self.status == DocumentStatus.ARCHIVED

    def section(self, section_id: str) -> DocumentSection | None:
        return next((s for s in self.sections if s.id == section_id), None)
