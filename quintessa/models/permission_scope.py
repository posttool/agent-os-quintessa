from enum import StrEnum


class PermissionScope(StrEnum):
    SESSION = "session"  # carries through the rest of one reasoning session
    PERSISTENT = "persistent"  # kept in memory for later sessions
