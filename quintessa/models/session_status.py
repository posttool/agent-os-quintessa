from enum import Enum


class SessionStatus(str, Enum):
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    COMPLETE = "complete"
    FAILED = "failed"
    STOPPED = "stopped"
