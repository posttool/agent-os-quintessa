from enum import Enum


class DocumentStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    WAITING = "waiting"
    COMPLETE = "complete"
    ARCHIVED = "archived"
