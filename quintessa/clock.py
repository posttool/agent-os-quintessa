from __future__ import annotations

import uuid
from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def parse_time(raw: object) -> tuple[datetime | None, str]:
    """An ISO time; one without a zone is taken as UTC. Returns the time, or
    None and why it could not be read."""
    if not raw:
        return None, ""
    try:
        at = datetime.fromisoformat(str(raw))
    except ValueError:
        return None, f"{raw!r} is not an ISO time"
    return (at if at.tzinfo else at.replace(tzinfo=UTC)), ""
