from enum import StrEnum


class ToolAuthor(StrEnum):
    """Who made or installed a tool."""

    SYSTEM = "system"
    AGENT = "agent"
    USER = "user"
