from enum import StrEnum


class ToolCallStatus(StrEnum):
    DONE = "done"
    IN_PROGRESS = "in_progress"
    NEEDS_USER = "needs_user"
    FAILED = "failed"
